# Edge Program — Implementation Guide

**Status:** v1.3 — engineering-ready
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Scope:** Ten epics (E1–E11; the former E8 — fantasy — is now its own guide). **E1–E5** are the *betting-edge* epics — pivoting the betting platform from "well-built, no demonstrated market edge" to "selective, validated, market-relative edge" (E1 overfitting audit, E2 per-side totals, E3 closing-line/CLV, E4 cross-book sharp-anchor, **E5 player props**). **E6–E7** extend the program beyond game betting: a feature-engineering audit (E6) and minor-league data ingestion to close rookie gaps (E7). **E9** is a living beta-user-request backlog (the product feedback loop, incl. the migrated A0 app/infra stories). **E10** is a parlay recommendation system (honest calculator first, recommender gated; beta-driven + differentiation). **E11** is the **infrastructure & cost-savings** epic (baseball dbt → lean-lakehouse migration; state-aware dbt builds — §6's execution home). The **Fantasy/Dynasty projections vertical** (formerly E8) now lives in `fantasy/fantasy_dynasty_guide.md` — it still depends on E7 (MiLB MLEs) + E2's machinery. Plus customer-facing framing, a market-SWOT **B2C value lens** (§7A), and the cross-session roadmap.
**Companion docs:** `edge_program_executive_summary.md` (higher-level strategy + honest likelihood-of-success read; its market SWOT mirrors §7A), `edge_program_technical_spec.md` (design rationale, Workstreams A–H), and the master `implementation_guide.md` (deep history; this guide references it, does not replace it).

---

## 0. How to use this guide (read first — applies to every Claude Code session)

This guide is **self-contained for the Edge Program**. A Claude Code session should be able to deliver any E1–E9 story from this file plus the specific source files each story names — without loading the 20k-line master guide.

- **Master guide is the historian, this guide is the worker.** Cross-references like `[[project_*]]` and "see Story 30.x" point into the master guide / memory; follow them only when a story tells you to.
- **Two-session model.** Up to two Claude Code sessions run simultaneously. §7 (Roadmap) assigns every story to a lane so the two sessions never touch the same files at the same time. Always check §7 before claiming a story.
- **New-session prompts.** Each epic's entry-point story carries a `▶ New-session prompt` fenced block — copy it verbatim into a fresh session to run that story standalone (same convention as the master guide's A0.4 / A2.x stories).

### 0.1 Non-negotiable conventions (inherited from the master guide)
- Use **`dbtf`**, never `dbt`. Always `--select`-scope local builds; never an unscoped `dbtf build` (it full-rebuilds every mart — the documented cost footgun).
- **Snowflake = OLAP only.** Access via the Snowflake MCP, fully-qualified `db.schema.table`, no `USE`. **Never add a live Snowflake query to a FastAPI request path** — request-time reads come from Railway PG (see 0.2).
- Run Python with **`uv run python`**. Hand any >1-min script/query to the user with the command shown. **Do not `git commit`/`push`** — the user owns git.
- **🟢 CI gates BEFORE handoff — REQUIRED (both tracks, 2026-06-18):** **never hand the operator red code.** Before the `⏭️ Operator handoff`, run the equivalent CI checks locally and confirm green: **Python → the Unit Tests CI job** (`uv run pytest`); **dbt → BOTH dbt-Build CI jobs — `state:modified+` (`dbtf build --select state:modified+`) *and* the compilation check (`dbtf compile`).** If a check fails, fix it (or, if it's a real blocker you can't resolve, say so explicitly in the handoff) — do not pass failing CI to the operator. State the CI result in the handoff.
- **Session closeout — REQUIRED (both tracks, 2026-06-18):** because sessions don't commit, **every session ends by telling the operator exactly what to run and what to commit**, or the repo drifts out of sync. End with an `⏭️ Operator handoff` block: **(a)** operator-run commands in order (Snowflake/dbt `dbtf --select …`/`uv run …`, >1-min flagged); **(b)** a copy-pasteable **`git add <paths>`** listing *every file the session changed/created that should be committed* — code, dbt models, `sub_model_registry.yaml`, `ablation_results/*.md`, guide/roadmap/`story_prompts.md` edits; **(c)** what to **NOT** commit (large artifacts — `*.pkl`/`*.parquet`/model binaries → S3/registry, gitignored); **(d)** for model work, the validation gate result; for app work, the changelog line + verify-after-deploy; **(e)** the **CI-gate result** (Python unit tests + both dbt-Build jobs green — see the CI rule above). (App sessions get this from `app_session_bootstrap.md`; model/standalone sessions must produce it from this rule.)
- Dagster in-process ops may **import packaged code only** (`[[feedback_dagster_import_only_packaged_code]]`).
- **Pipeline failure-handling contract (E11.7, 2026-06-22 — enforce on every new op/dbt test):**
  - **HALT** (raise Exception / fail op) = serving-critical ONLY — `predict_today`, feature store `dbt run`, serving marts, `write_serving_store`, `signal_freshness_check`, contract-guard.
  - **WARN-but-continue** = peripheral data-quality — non-serving ingestion (weather, OAA, bio ranges), the non-blocking `dbt test` step, user-bet settlement, narrative generation.
  - **ALERT-loud-but-continue** = any skip that hides work (missing env/URL, unreachable runner, no-op) — MUST emit `context.log.warning(...)` or write to stderr; NEVER a silent `print()`/`pass`.
  - No in-process `dbtf` — all dbt goes through `pipeline/ops/_dbt_exec._run_dbt`. On build days, serving-critical step is always `dbt run` first; `dbt test` is non-blocking (INC-6). Canonical op→tier map lives in CLAUDE.md.
- **Honest-framing rule (product-wide, non-negotiable):** the point models have **no demonstrated market edge** (`best_alpha = 0`). Nothing user-facing may claim a win-rate or edge, or frame "+EV"/"high conviction"/"high P(CLV)" as "place this bet." US betting is manual (`[[feedback_no_auto_betting]]`). Every new model/signal is a **transparency / confidence** surface unless and until it clears the live gates in §5.
- **Market-blind by default (architecture Principle 3, non-negotiable):** the market already prices in everything our baseball features contain, so **every model that is not itself modeling market behavior is market-blind** — NO odds, implied-probabilities, line-movement, consensus, or book features in its inputs. A non-market model trained on the line just *relearns the line* (circularity/leakage) and can add nothing orthogonal — the root reason the current stack can't beat the market. Market data is permitted **only** in the market models (**E3, E4**, and CLV/meta) and at the **evaluation/CLV-gating** layer (e.g. E2.6, E5.4). Enforce with a `CONTRACT-GUARD`-style assertion on every non-market feature matrix. Applies to E2, E5, E6, E7, E8.
- **Cost-first (see §6):** Dagster **coordinates**; heavy execution runs on **Railway / EC2-batch / DuckDB / S3-Parquet**, not on Snowflake compute or Dagster+ run-minutes. Every new recurring job states where it runs and its break-even.

### 0.2 Application architecture (the "Credence" app — for any app-repo story)

> ## 🚨 APP TARGET — READ FIRST (every `[App]` story) 🚨
> Three things share confusingly similar paths. **Two are live; one is dead.**
> - ✅ **UI / anything user-facing → `frontend/` ONLY** (Next.js on Vercel). UI lives in `frontend/app/**`, `frontend/components/**`, `frontend/lib/**`, `frontend/hooks/**`, `frontend/data/**`.
> - ✅ **API / backend → `app/backend/`** — the **live FastAPI** service (deployed to Lambda via `infrastructure/lambda/deploy.sh`; entrypoint `app.backend.main`). Edit this for backend work.
> - ⛔ **DEPRECATED legacy Streamlit UI → `app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`** — not deployed, not the product. **DO NOT EDIT** unless a story *explicitly* says "legacy Streamlit."
> - **Footgun (bit a session 2026-06-18):** `app/` is **half-alive** — `app/backend/` is the live API, but the dead Streamlit UI files sit right next to it at the top of `app/`. And Next.js has its *own* `frontend/app/` router dir. **"The app's UI" is always `frontend/`, never `app/home.py` / `app/pages/`.**
> - **First action in any app session:** `cat frontend/package.json` → confirm Next.js (`"next"` in deps, `"dev": "next dev"`). If doing **UI** work and you open `streamlit_app.py` / `st.set_page_config` / `app/home.py` / `app/pages/*.py`, **STOP — wrong place → `frontend/`.**
> - **A change is not done** until it works in the right live target (`frontend/` for UI, `app/backend/` for API) **AND, if the end user would notice it, a `frontend/data/changelog.json` entry is added** as the final step. The Streamlit app never gets a changelog entry (it isn't shipped).

- **Backend:** AWS API Gateway + Lambda (`credence-prod-lambda-api`, us-east-1), **FastAPI source in `app/backend/`** (entrypoint `app.backend.main`). Deploy via `infrastructure/lambda/deploy.sh`. *(Note: `app/backend/` is live; the rest of `app/` is legacy Streamlit — see banner.)*
- **Frontend:** **Next.js on Vercel, lives in `frontend/`** (auto-deploys on push to main). This is the only shipped UI. *(The top-level `app/` Streamlit UI is legacy/deprecated — see the banner above.)*
- **Serving (two-tier):** **Railway PostgreSQL** = primary OLTP serving store (FastAPI reads PG first); **S3** (`credence-prod-s3-api-cache`) = fallback. Dagster reverse-ETLs precomputed picks/detail into PG via `scripts/write_serving_store.py` after each pipeline run. Read order: **PG → S3 → Snowflake** (Snowflake last-resort only, never at request time in prod). PG tables: `daily_picks`, `game_detail` (JSONB), `performance_summary`, `user_portfolios`.
- **DynamoDB:** bet log (`credence-prod-dynamo-user-bets`) + users (`credence-prod-dynamo-users`) only.
- **Changelog:** any non-admin user-facing change adds an entry to `frontend/data/changelog.json` as its final step (the weekly changelog page, A0.4.26). **Weeks group Monday→Monday:** the `week` value is the **Monday of the week the change ships** (not the literal ship date). Append your item to the existing block for the current Monday if one exists; only create a new block when the current Monday has none. (E.g. anything shipped Tue–Sun goes under that week's Monday label.)

### 0.3 App/UI work is a separate session — its prompt is emitted by the upstream session
**Rule:** any application/UI work runs in a **separate Claude Code session** (the Credence app repo), distinct from the model/backend session that produces the data it renders. Each app surface is its own story (tagged 🧩 *separate app session* — e.g. E2.7, E5.5, E8.7, E9.x) with its own `▶ App-session prompt`.

**The app-session prompt is NOT hand-written in advance — the upstream model/backend session *generates* it as its final step.** Only the session that just built the interface knows the *actual* served contract (exact column names, payload shape, the Railway-PG table it wrote, the serving path), so it authors a precise prompt instead of a guess that drifts from reality.

**Mechanics:**
1. Every model/backend epic that feeds an app surface ends with a **final handoff task**: *"Generate the `▶ App-session prompt` for `<app story>` and write it into §`<app story>` of this guide, filled with the real served columns / payload / PG table / serving path you produced."*
2. Until that runs, the app story's prompt block reads **`⏳ to be generated by the upstream <story> session on completion`** — do not hand-author it.
3. The app session then copies the now-filled prompt into a fresh app-repo session and builds, following §0.2 (architecture) + the honest-framing rule + the changelog step.

This keeps app prompts accurate (no drift from the real contract) and cleanly separates the two repos/sessions.

**One fresh session per app story (workflow, 2026-06-18):** app stories are run **one at a time, each in its own clean session** — paste the persisted **application-session bootstrap prompt (`app_session_bootstrap.md`)** first (it carries the §0.2 app-target guard + §0.1 conventions + the changelog DoD + the operator-handoff closeout), then **exactly one** `▶ Story prompt`; build, report, end the session. Do **not** let a single long-lived app session chain multiple stories — context drifts and stories bleed together (and it's how a session ended up editing the deprecated Streamlit `app/`). Pull the next card into a new session.

**Operator-handoff closeout (required, 2026-06-18):** the session never deploys, commits/pushes, or runs >1-min jobs itself — instead it **ends with a single `⏭️ Operator handoff` checklist** of everything the operator must run, copy-pasteable and in order: 🔧 Lambda rebuild+deploy (`./infrastructure/lambda/deploy.sh`) if `app/backend/` changed; 🗄️ scoped `dbtf run --select …`; ▶️ `uv run python …` scripts (with env/date args, >1-min flagged); 🌱 one-off infra/migrations; 📦 the exact **`git add <paths>`** for the files to deploy (operator commits/pushes); 📝 changelog line (or "N/A"); ✅ what to verify after deploy. Full template lives in `app_session_bootstrap.md`.

**Exception — pure app-repo stories:** items that live entirely in the app repo and compute from an *already-served* contract (e.g. the E9.x beta-backlog stories like E9.1, which derive the breakeven price from the `p` already in the A0.4.32 payload) have **no model/backend upstream to emit their prompt** — they're authored and built directly in an app session. The handoff above applies only when a model/backend session produces a *new* served contract the app will render.

---

### 0.4 One prompt per story (standalone-runnable)
**Convention (2026-06-18):** we prioritize and schedule at the **story** level (Trello cards), so **every story must be independently runnable** — when a story is pulled off the board, it carries its **own `▶ Story prompt`** that a fresh Claude Code session can execute *without* the rest of its epic. The epic-level prompts remain only as **orientation/context**, not the run unit.
- **New stories embed their `▶ Story prompt` inline** with the story (as the E9.x stories do).
- **Existing epic sub-stories:** their per-story prompts are collected in **`story_prompts.md`** (one `▶ Story prompt` per open story). The epic prompt stays as background.
- A story prompt is **compact** — it inherits shared context *by reference* (don't repeat §0/§5/§6). Template:
```
▶ Story prompt — <ID> <title>   [lane: Model-A | Model-B | App | Serving]
Read: edge_program_implementation_guide.md §<ID> (this story) + §0 (conventions) + §5 (gates) + §6 (cost)
      [+ edge_program_technical_spec.md WS-<x> if modeling; + the master-guide refs the story names].
Do: <condensed task list>.
Gate/AC: <the story's AC + which live gate it must clear — E1 PBO/DSR etc.>.
Conventions (per §0.1): dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run python; hand >1min
scripts to the operator; do not git commit/push [+ market-blind if a non-market model; + honest-framing if user-facing].
CI before handoff (per §0.1): confirm GREEN locally first — Python → `uv run pytest` (Unit Tests CI);
dbt → `dbtf build --select state:modified+` AND `dbtf compile` (both dbt-Build CI jobs). Never hand off red code.
Closeout (per §0.1): END with an ⏭️ Operator handoff — the run-order commands + a copy-pasteable `git add <paths>`
of EVERY changed/created file to commit (code, dbt, sub_model_registry.yaml, ablation_results/*.md, doc edits),
what NOT to commit (artifacts → S3/registry), the CI-gate result, and the gate result (model) / changelog + verify (app).
```
> **App-story prompts MUST also carry the app-target guard (per §0.2):** *"APP TARGET: UI → `frontend/` (Next.js) ONLY; backend → `app/backend/` (live FastAPI). Do NOT edit the legacy Streamlit UI (`app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`). First action: `cat frontend/package.json` to confirm Next.js; if doing UI work and you open `app/home.py`/`app/pages/*.py`, STOP — wrong place. If the end user would notice the change, add a `frontend/data/changelog.json` entry as the final step."* Put this in every `[App]` `▶ Story prompt`.

### 0.5 Modeling bake-off discipline (🔬 NON-NEGOTIABLE for any story that BUILDS or SELECTS a predictive model)

**The standard (operator 2026-06-24, after the E5.2 lapse):** initial modeling is a **bake-off, never a single architecture.** A story may *suggest* a structure, but the session must still search — one architecture that misses its gate is **not** evidence the problem is null; that conclusion is only earned after the bake-off + ablation + tuning across a candidate set all come up empty. The canonical exemplar is **E1.9 v6** (XGBoost / LightGBM / CatBoost / NGBoost / GLM-elastic-net / stack, purged CV, per tier → Optuna → PBO/DSR gate — glm/ngboost *won* the bake-off, they weren't assumed). Every model story follows that shape:

1. **Pre-register a CANDIDATE SET (≥3 model classes)** appropriate to the target *before* running — and write it in the prompt. A prescribed structural/generative form (e.g. E5.2's K-rate × batters-faced compound) is **ONE candidate among several**, not the whole search; always include at least one direct learned model as a foil (a structural model that can't beat a plain GBM on calibration hasn't earned its complexity). For distributional targets, the candidates are parametric/structural forms (NegBin / Beta-Binomial / compound / direct-count GBM), judged on PIT / calib_80 / CRPS.
2. **Feature ablation, not default inputs** — sweep the input/contract set (candidate features on/off), don't just run one feature list. Reuse `derive_clustered_contract.py` / the E13.4 `incremental_lift_eval.py` harness where it fits.
3. **Optuna hyperparameter optimization (bounded trials) per candidate** — compare *tuned* models, never library defaults (the v6 standard). State the trial budget + search space in the handoff.
4. **Pick on the metric under purged/embargoed walk-forward CV (E1.1), PER TIER** where serving is tiered (pre_lineup vs post_lineup — don't grade a morning model on dense re-reads; the E12 optimistic-0.42 trap).
5. **Guard the SEARCH against overfitting: PBO < 0.2 AND DSR > 0 (E1.4)** — both deflate for the number of configs tried, so a wide bake-off is *safe* (it's priced in), but cherry-picking the best-of-many without the deflation is not. Forward CLV stays the cashability gate for any *edge* claim.
6. **A clean ("trustworthy") null** = the *whole* candidate set, tuned + ablated, fails the gate — with the mechanism named (e.g. "log5 already captures 86% identity by construction"). Report what was tried + the per-candidate scores; never abandon on the first architecture's miss.

> **Calibration ≠ edge still holds:** the bake-off picks the best-*calibrated* model (product value); the *edge* gate (PBO/DSR + forward CLV) is the separate downstream hurdle. **Exceptions (no full bake-off needed):** pure-registration/backfill stories (E2.5), cheap-closure re-evaluations of already-built sub-models (E13.3), or a story explicitly scoped as a harness/eval rather than a model build. When in doubt, bake off.

**Every `[Model-*]` `▶ Story prompt` that builds or selects a model MUST carry a one-line:** *"🔬 BAKE-OFF (per §0.5): pre-register ≥3 candidate classes [list], Optuna-tune each, feature-ablate, pick on [metric] under purged CV per tier, PBO<0.2/DSR>0; a single architecture's miss is NOT a null."*

**💾 DATA-ACCESS / COST HYGIENE (per §0.5 + the "minimum Snowflake until profitable" principle — applies to ALL model training, and is ESPECIALLY load-bearing in a bake-off):** a bake-off runs N candidates × K folds × T Optuna trials — assembling the training matrix from Snowflake *inside* that loop means N×K×T warehouse hits. **Don't.**
1. **S3-FIRST:** if the data already lives in the lakehouse (S3) — the `mart_pitch_*` Statcast marts (W1), the PA substrate (E13.12, duckdb-only), the prop/derivative backfills (E5.1/E2.0), `stg_batter_pitches` — read it FROM S3 via DuckDB, **NOT Snowflake.** New/heavy model-training transforms default off-Snowflake (the E13.2 lakehouse-only posture).
2. **ONE PULL → PARQUET, then reuse:** if a Snowflake pull is unavoidable, do it **exactly once** — materialize the assembled, leak-clean training matrix to a local/S3 **parquet**, and have **every bake-off candidate + every ablation + every Optuna trial + every CV fold read that parquet**, never re-query Snowflake per-candidate/per-trial. The pull is a single up-front step in the operator-run orchestration script, before the candidate loop.
3. **Cache the assembled matrix, not raw tables** — pull the joined/feature-built frame once (the expensive part), persist it, and iterate models against the cached frame. Document the parquet path + row count in the handoff so the operator can reuse it across sessions.

> This is the cost analogue of the bake-off: the discipline that makes a *wide* search affordable. State the data source (S3 vs the one Snowflake pull) + the cached-parquet path in every model handoff.

**Every `[Model-*]` `▶ Story prompt` MUST ALSO carry:** *"💾 DATA (per §0.5): S3-first via DuckDB where available; else ONE Snowflake pull → parquet that all bake-off candidates/folds/trials reuse — never re-query per candidate."*

**🧬 FEATURE-SELECTION DISCIPLINE (the feature-axis complement to the bake-off — threads the SAME two failure modes).** Feature selection is genuinely needed and is **not** optional, but it must avoid both horns: ❌ **(A) "this feature set failed, oh well"** — abandoning on ONE arbitrary contract is as invalid as testing one architecture; ❌ **(B) permute features until something looks good** — open-ended subset search is the multiple-comparisons / overfitting machine. The discipline that sits between them:

1. **Pre-register the ablation, don't open-search.** Before running, write down the base contract + a **BOUNDED, hypothesis-driven set of candidate changes** — each ADD a named feature with a *rationale* (e.g. TTO penalty, catcher framing), each DROP a redundancy cluster — **in the prompt.** A handful of pre-committed, reasoned ablations; never "try every subset until green."
2. **Selection is PART of the model → fit IN-FOLD + COUNT it in the deflation.** Compute importance / run the add-drop on **train folds only** (never peek at the eval fold — selecting features on the full set leaks). Every feature config tried is a **trial that PBO<0.2/DSR>0 deflates for** (DSR penalizes the number of configs) — this is precisely what makes a *wide* ablation safe, identical to the bake-off logic. A feature that lifts in-sample but doesn't survive purged CV + the deflated gate is **rejected.**
3. **Mechanical rule, not hand-pruning** (E1.8's hard-learned bug: hand-pruning off a stale ranking shipped a wrong contract). Use the reproducible instruments: **`derive_clustered_contract.py`** (clustered-MDA non-noise-cluster rule + leakage guard) for REMOVAL/contracts; **`incremental_lift_eval.py`** (E13.4) for ADDITION (does feature X lift beyond the noise floor, PBO/DSR-guarded). **Prefer EMBEDDED selection** — elastic-net L1/L2, tree importance/SHAP, or **Optuna-tuned regularization strength** (a continuous knob that does selection without a discrete-subset explosion) — over brute-force wrapper search.
4. **A "feature set failed" is only TRUSTWORTHY if it failed the disciplined ablation** — the pre-registered candidate changes, tested in-fold with deflation — not a single list. Report what was tried + per-config scores + the **mechanism** (cf. E13.2b: "the zone profiles are orthogonal-but-inert — genuinely new info that lifts nothing" is a real null; "we only tried one contract" is not).

> Net: feature selection is a **bounded, pre-registered, in-fold, deflation-counted ablation run on the existing harnesses** — wide enough to never "give up on one set," disciplined enough to never fish. Same spirit as the bake-off: try the candidates honestly, let the deflated gate decide, name the mechanism.

**Model prompts that ablate features carry:** *"🧬 FEATURES (per §0.5): pre-register the candidate adds/drops [list + rationale]; select IN-FOLD via `derive_clustered_contract.py`/`incremental_lift_eval.py` (or Optuna-tuned regularization); every config counts toward PBO/DSR; a single contract's miss is NOT a null."*

---

## 1. Strategic thesis (why these epics)

The system has run **13 independent head-on no-edge confirmations** (4 H2H: Epics 11, 16B.7, 28.4, 28.5; ~9 totals: 10.6, 16B, 17, 27.3, 10.10, …). The promotion gate correctly judges accuracy-to-truth; the champions are honest. The conclusion is structural: **the full-game moneyline and total are efficiently priced, and ~10K noisy labels cannot out-predict that one number.** A better likelihood (Bradley-Terry, PyMC NegBin) cannot manufacture absent signal.

So the Edge Program stops optimizing the point model against the closing line and attacks the places edge can still exist:

| Epic | Name | Lever | New target |
|------|------|-------|-----------|
| **E1** | CV-Hygiene & Overfitting Audit | Quantify how much "getting closer" is multiple-testing noise. **Gates E2–E5 go-live.** | (audit, not a model) |
| **E2** | Per-Side Generative Totals | Compete on numbers books price *lazily* (F5, team totals, alt-lines) via an honest full distribution. | per-side run distributions → convolved total |
| **E3** | Closing-Line / CLV Model | Predict the market's own move (open→close) — far higher SNR than the game. | Δ(open→close), P(beat close) |
| **E4** | Cross-Book Sharp-Anchor | Bet the soft book (Bovada/Caesars/FanDuel) toward Pinnacle when they diverge. | `pinnacle_fair − book_implied`, per book |
| **E5** | Player Props & Derivative Markets | Price player props (K's, total bases, hits, outs) against the book line — the softest, most numerous markets. | per-prop distribution vs book line; edge + CLV |

**Resolved decisions (2026-06-17):** Bovada = book the operator bets; beta users on Caesars + FanDuel; **Pinnacle = sharp anchor** (live, timestamped, via The Odds API `regions=eu`; history to 2024, extendable). Strictly **advisory, B2C** (no auto-betting). Heavy compute runs off-warehouse (§6).

### 1A. Program extensions (E6–E7) + the spun-out Fantasy vertical

E1–E5 are the *betting-edge* epics. Three further epics extend the program along axes that aren't "find game-betting edge" — they sharpen the foundation and open a second product line. (See **§7A** for the market SWOT + the B2C-value argument that the fantasy/projections vertical may be the highest-value of all.)

| Epic | Name | What it is | Why now |
|------|------|-----------|---------|
| **E6** | Feature-Engineering Audit | A **standalone audit** of all ~690 features for overlooked engineering opportunities (interactions, transforms, missing context, redundancy). Produces a prioritized backlog, not code. | Cheap, high-leverage: we've never systematically swept the feature surface. Reuses E1.3 clustered importance. Kept separate so it doesn't bloat the edge epics. |
| **E7** | Minor-League (MiLB) Data Ingestion | Ingest AAA/AA performance + AAA Statcast + prospect data, and build minor→major translation factors (MLEs) to close the **rookie/call-up data gap** (today filled by generic EB priors). | Better rookie inputs improve the betting sub-models *and* are the prerequisite for credible prospect projections in E8. |
| **(E8 → own guide)** | Fantasy / Dynasty Projections | Spun out to `fantasy/fantasy_dynasty_guide.md` (F1–F8). A second **B2C vertical**: distributional, multi-year, prospect-aware player projections for fantasy (esp. Dynasty). | Its own beast (own data context + validation bar + roadmap; seed for multi-sport fantasy). Still depends on E7 (MiLB MLEs) + E2 machinery; per §7A the highest-value B2C bet. |

**Dependencies:** E7 → **Fantasy F4** (prospect projections need the MiLB MLEs). E6 feeds all modeling (betting + projections). The Fantasy vertical (`fantasy/fantasy_dynasty_guide.md`) reuses E2's distributional machinery + the Story-33.1 playing-time model. It **has now graduated into its own guide** (it was the largest new scope, has its own data context + validation bar, and seeds multi-sport fantasy).

---

## 2. Non-technical end-user explanations (one per track)

Plain-language copy for talking to prospective customers who don't know this kind of modeling. Honest-framing rule applies — these describe *what the user gets*, never a promised win-rate.

### 2.1 "How sure is the model?" — Overfitting audit (E1)
*Customer language:* "Anyone can build a model that looks brilliant on past games and falls apart on tomorrow's. Before we show you a number, we stress-test our models the way a careful investor stress-tests a strategy — we check that an apparent edge isn't just luck from trying many ideas. When Credence tells you it's confident, that confidence has been earned against a deliberately tough, honest test, not a flattering one." *Why it matters to them:* it's the difference between a tipster's hot streak and a measured process. E1 is invisible plumbing, but it's the reason every other number on the platform can be trusted.

### 2.2 "The full picture of a game, not just one number" — Per-side distributions (E2)
*Customer language:* "Most sites give you a single prediction: 8.5 runs, over or under. Credence shows you the whole range of how a game could realistically go — how likely a low-scoring pitchers' duel is versus a slugfest — and breaks it into how many runs *each* team is likely to score. That lets us price bets the big sites treat as an afterthought: first-5-innings totals, individual team totals, and alternate lines. You see the distribution and the few factors driving it, so the pick is transparent, not a black box." *Why it matters:* depth and explainability; and it opens the softer markets where value is more likely to exist.

### 2.3 "Catching the line before it moves" — Closing-line / CLV (E3)
*Customer language:* "Sportsbook lines drift through the day as money and news come in. The single best sign you got a good price is that the line later moved in your favor — pros call this 'beating the closing line.' Credence focuses on spotting those moves *before* they happen, so you can act early. We measure ourselves on whether the market agrees with us by game time, which is a faster, more honest scoreboard than chasing win/loss results." *Why it matters:* reframes "good bet" as "good price," which is both more achievable and what sharp bettors actually optimize.

### 2.4 "Borrowing the sharps' price" — Cross-book sharp-anchor (E4)
*Customer language:* "Not all sportsbooks are equally sharp. A handful (like Pinnacle) set extremely accurate prices because professionals bet into them. The recreational books most people use — Bovada, Caesars, FanDuel — are slower to update. Credence watches the sharp price and flags when *your* book is offering a number that lags it, on the side the sharp money favors. You pick your sportsbook; we show you where it's out of step with the sharpest price in the market." *Why it matters:* this is the most intuitive and most likely real edge — and it's personalized to the book each user actually bets.

### 2.5 "Down to the individual player" — Player props (E5)
*Customer language:* "Beyond who wins and how many runs, you can bet on individual players — will this pitcher record over 6.5 strikeouts, will this hitter get 2+ total bases. These markets get a fraction of the attention the main lines do, so the prices are looser. Credence already models every player in depth — recent form, the specific pitcher-vs-hitter matchup, expected playing time — so we show you our projected range for a player next to the line your book is offering, with the key reasons why." *Why it matters:* props are where our player-modeling depth and the market's thin attention line up best — and the projections live right on the player pages users already browse.

### 2.6 "Projections that see the whole farm system" — Fantasy & Dynasty (E8)
*Customer language:* "Fantasy baseball — especially Dynasty leagues, where you keep players for years — lives and dies on projections, and most tools give you a single number with no sense of risk or upside. Credence projects every player as a *range* (a likely floor, midpoint, and ceiling) across the rest of the season and into future years, and — crucially — it does the same for prospects in the minor leagues by translating their minor-league performance into what it's likely to become in the majors. So when you're deciding whether to trade for a 21-year-old in Triple-A, you see a real, risk-aware projection, not a gut call." *Why it matters:* projections are the core fantasy need, the Dynasty/prospect angle is underserved, and the minor-league translation is the hard part most competitors skip.

> **E6 (feature audit) and E7 (minor-league ingestion) are internal enablers** — they sharpen the models and feed E8's projections, so they don't get their own customer-facing pitch. E7's payoff reaches customers *through* E8's prospect projections.

---

## 3. Epic E1 — CV-Hygiene & Overfitting Audit  ✅ **COMPLETE 2026-06-18** — gate set  **[Track R · gates E2–E5 go-live]**
> **Audit verdict (E1.1–E1.6 built + validated) — ⚠️ two findings revised 2026-06-18 by E2.1b:** **(1)** ~~no leakage in any champion~~ → **REVISED: a *within-game* leak was present and purged CV missed it** — `bp_eb_xwoba` weights reliever EB by `outs_in_game` (a feature peeking at its own row; purged CV only guards temporal/cross-fold leakage). See E2.1b + the de-leak card **E1.7**; **(2)** all three are **massively over-parameterized** — ~370 feats → **14 / 31 / 19** with no loss → **re-promote on the slim contracts**, *but* **re-derive the prune after the de-leak** (the leaky feature contaminated the importance ranking the slim sets were chosen from); **(3)** ~~bullpen EB dominates every target → the clearest signal-investment direction~~ → **❌ RETRACTED: that #1/#2 rank was the leak.** De-leaked, `bp_eb_xwoba` importance collapses to noise (0% retained); the only real pre-game bullpen signal is **data-depth (`coverage_pct`/`uncertainty`), and it's modest**; **(4)** **history extension (E1.6) is a wash** → don't extend history. **Revised net: the play is the E2 per-side-totals *architecture* (honest distribution/derivatives), not a bullpen signal; and E1's most valuable surfaced action is the de-leak (E1.7) + a full leakage sweep (E1.8).** PBO/DSR + purged-CV on record → E2–E5 go-live unblocked (each still clears its own gate).

**Goal:** Produce honest CV and a trustworthy *number* on every claimed edge, so no E2–E5 strategy ships on multiple-testing noise. **This epic blocks the go-live (not the build) of E2–E5.**

**Why first:** many model variants have been tried; each is a chance to find a spurious edge (AFML ch. 11–12). Two problems: (a) walk-forward CV still leaks via overlapping feature windows; (b) there is currently no metric for "is this edge real?" E1 fixes both.

> **Build status (all code + tests landed; 49 new tests green):** E1.1–E1.4 utilities and scripts are written and unit-tested on synthetic data. The three **validation runs hit Snowflake + retrain NGBoost (minutes each) → handed off to the operator** (commands below); they produce the actual `ablation_results/*.md` numbers and the leakage/PBO/DSR figures that gate E2–E4. The standing `overfitting_dashboard.md` is seeded; `purged_cv_recalibration.md` / `clustered_feature_importance_*.md` are generated by the hand-off runs.
>
> **Operator hand-off commands** (`uv run`, Snowflake creds, off-warehouse — first run caches the training matrix to local parquet via `training_cache`):
> ```
> # E1.5 — honest re-baseline of all three champions (standard vs purged vs purged+weighted CV)
> uv run python betting_ml/scripts/rebaseline_purged_cv.py --target all
> # E1.3 — clustered MDA under purged CV (one target per run; parallelizable)
> uv run python betting_ml/scripts/clustered_feature_importance.py --target total_runs
> uv run python betting_ml/scripts/clustered_feature_importance.py --target home_win
> uv run python betting_ml/scripts/clustered_feature_importance.py --target run_diff
> # any gate eval can now opt into purged CV + uniqueness weights:
> uv run python betting_ml/scripts/promotion_gate_eval.py --target total_runs --purged-cv --uniqueness-weight
> ```

> **✅ RESULTS — operator ran the full E1 audit 2026-06-17:**
>
> **E1.5 re-baseline (leakage):** all three champions CLEAN — the purged-vs-standard metric delta is within the noise floor on every target (`home_win` −0.0005 Brier, `run_diff` +0.0076 MAE, `total_runs` +0.0179 MAE — totals leans most on rolling form, right at its 0.02 floor, as predicted). **No champion's track record was a near-boundary-leakage artifact.** Sample-uniqueness weighting (E1.2) HURTS `home_win`/`run_diff` and is ~flat on `total_runs` → do **not** adopt it for the champions (kept as a tool for E1.6 / future bagged models).
>
> **E1.3 clustered importance — every champion is 90–96% overfitting surface.** Pruning each to its signal-bearing clusters (paired-bootstrap CI > 0) and gating the slim contract vs the deployed ~370-feat champion under purged CV:
>
> | Target | Parent → prune | Pooled Δ vs champion | Floor | Verdict |
> |---|---|---|---|---|
> | `total_runs` | 111 → **14** | +0.0019 MAE | 0.02 | tied — value-preserving (also calibration-preserving: cov80 0.775 vs 0.759, PIT-KS/NLL slightly better) |
> | `home_win` | 209 → **31** | −0.0002 Brier | 0.002 | tied — value-preserving |
> | `run_diff` | 167 → **19** | **−0.0215 MAE** | 0.02 | **better — clears the effect floor on every fold; HOLD only because the CI upper bound nicks +0.0025** |
>
> Pruned contracts written: `betting_ml/models/{total_runs,run_differential}/feature_columns_ngboost_pruned_clustered_2026.json`, `betting_ml/models/home_win/feature_columns_xgb_classifier_pruned_clustered_2026.json`.
>
> **⭐ Cross-target finding:** `home_bp_eb_xwoba` + `away_bp_eb_xwoba` (bullpen EB quality) are the **#1 and #2 feature on ALL THREE targets**, and the EB bullpen block (xwOBA + uncertainty + coverage) dominates each signal set. The platform's models are, functionally, **bullpen-quality models with a long near-noise tail.** Implications: (a) invest modeling effort in the bullpen EB posteriors; (b) the dropped ~350 features are pure overfitting surface — for `run_diff` they were *actively harmful*; (c) this independently re-confirms the full-game point models are signal-thin and ceilinged → reinforces the E2 per-side-generative pivot. **`run_diff` is a legitimate promotion candidate** (simpler *and* better) if re-tuned on its 19 features; deferred — point accuracy is ceilinged so it doesn't change the edge story.

### E1.1 — Purged & embargoed walk-forward CV  ✅ (code)
**Problem:** rolling features (`*_7d/14d/30d`, `mart_team_rolling_*`, `mart_bullpen_*`) make a test-day game's vector overlap the training labels of the immediately preceding window. Season walk-forward doesn't remove near-boundary leakage.
**Tasks:**
- [x] `betting_ml/utils/cv.py::PurgedWalkForwardSplit` — forward-chained (keeps the season outer loop); **purge** the prior-season boundary band that carries forward into the eval season's rolling features (anchored to the last training game-date, so the offseason gap doesn't make the band vacuous — see the module docstring); **embargo** `embargo_days` (default 3) after the test fold.
- [x] Per-feature window registry (`feature_window_days` / `max_feature_window`) parses `_7d/_14d/_30d/_3yr` so the purge band is feature-aware, not a blanket 30d.
- [x] Wired as an opt-in split into `promotion_gate_eval.py::walk_forward_gate` + `walk_forward_calibration` via `--purged-cv` (`make_gate_splitter`); recommended for all new models.
**AC (operator run):** `rebaseline_purged_cv.py` re-scores champions under purged CV; the metric delta vs current CV is the leakage estimate in `ablation_results/purged_cv_recalibration.md`; near-boundary-dependent champions flagged when the delta exceeds the noise floor. **Note (validated on synthetic):** with season-granularity folds the offseason already provides a natural embargo, so the purge targets exactly the carried-forward prior-season tail (~30 game-days); expect the measured leakage to be modest — that *quantified* number is the deliverable.

### E1.2 — Sample-uniqueness weighting (sequential bootstrap)  ✅ (code)
**Problem:** games aren't i.i.d. (consecutive starts, intra-series games, shared bullpen state).
**Tasks:**
- [x] `betting_ml/utils/sample_uniqueness.py::compute_sample_uniqueness` — per-game concurrency → `avg_uniqueness ∈ (0,1]` (AFML §4.3); `attach_sample_uniqueness` writes the canonical `sample_uniqueness` column, drift-guarded by `test_sample_uniqueness_parity.py` (mirrors `season_normalization`).
- [x] `sample_weight=avg_uniqueness` threaded into the XGBoost/NGBoost fits via the adapters (`--uniqueness-weight`, applied to BOTH arms for a fair comparison); `sequential_bootstrap()` for bagged variants.
**AC (operator run):** `rebaseline_purged_cv.py` reports `purged+weighted` alongside `purged`; promotion still via `evaluate_promotion`; the weight delta documents any calibration change. Production trainers adopt `attach_sample_uniqueness` on promotion of the weighted recipe.

### E1.3 — Clustered feature importance (MDA)  ✅ (code)
**Problem:** ~690 features, heavily collinear (`home_*`/`away_*` mirrors, multi-window dupes). Near-uniform stacking weights = diluted single-feature importance. MDI is biased; use **MDA on clusters**.
**Tasks:**
- [x] `betting_ml/scripts/clustered_feature_importance.py`: hierarchical cluster on `1−|ρ|` → clustered MDA (shuffle each cluster jointly under purged CV E1.1; model fit ONCE per fold, re-predict per permutation — fast + sound). Reads the training matrix from parquet cache (off-warehouse, §6).
- [x] Outputs ranked cluster importance → `ablation_results/clustered_feature_importance_<target>.md` + JSON.
**AC (operator run):** clusters whose paired-bootstrap CI crosses 0 are flagged noise → drop/consolidate; the report states the dimensionality cut; re-run `promotion_gate_eval.py --purged-cv` on the pruned contract to confirm no accuracy regression before promoting the smaller set.

### E1.4 — PBO (CSCV) + Deflated Sharpe  ✅ (code)  **[the program's go-live gate]**
**Tasks:**
- [x] `betting_ml/utils/overfitting.py::pbo_cscv()` — Probability of Backtest Overfitting via Combinatorially-Symmetric CV (AFML §11.4) over a per-config performance matrix; caps `max_combos` to bound cost (§6).
- [x] `…::deflated_sharpe()` — DSR (AFML §14) deflating observed Sharpe by trial count + non-normality (skew/kurtosis), for any *betting* strategy (E2 derivatives, E3/E4 selective bets).
- [x] Standing report `ablation_results/overfitting_dashboard.md` (seeded) + `render_overfitting_dashboard()` to regenerate whenever a strategy is proposed.
**AC + thresholds (encoded as `PBO_SHIP_TO_SHADOW=0.5`, `PBO_SHADOW_TO_LIVE=0.2`, `DSR_CONFIDENCE=0.95`):** ship-to-shadow requires **PBO < 0.5**; shadow-to-live requires **PBO < 0.2 AND DSR ≥ 0.95 AND** the existing live-CLV gate (§5). No E2–E4 strategy goes live without a PBO and DSR on record.

### E1.5 — Re-baseline current champions honestly  ✅ **DONE 2026-06-18** (no leakage; champions clean; slim contracts win)
**Tasks:** [x] `betting_ml/scripts/rebaseline_purged_cv.py` re-runs `home_win` v5, `run_differential` v5, `total_runs` through standard / E1.1 purged / E1.1+E1.2 weighted CV and writes the honest baselines. **AC (operator run):** updated champion baselines in `purged_cv_recalibration.md` (and `model_registry.yaml` notes) — the numbers the Edge models must beat.

```
▶ New-session prompt — Epic E1 (copy into a fresh model-repo Claude Code session)

You are building Epic E1 (CV-Hygiene & Overfitting Audit) of the MLB Edge Program.
GOAL: honest CV + a trustworthy overfitting number that gates every later Edge strategy.

Read first:
  1. edge_program_implementation_guide.md — Epic E1 in full (§3) + §0 conventions + §5 gates
  2. edge_program_technical_spec.md — Workstream A (the rationale)
  3. betting_ml/scripts/promotion_gate_eval.py + betting_ml/utils/promotion_gate.py
     (evaluate_promotion, walk_forward_gate — you extend these, not replace them)
  4. betting_ml/utils/season_normalization.py (the drift-guarded-column-list parity pattern to mirror)

Build, in order: E1.1 PurgedWalkForwardSplit (betting_ml/utils/cv.py) → E1.2 sample-uniqueness
weights → E1.3 clustered_feature_importance.py → E1.4 overfitting.py (pbo_cscv + deflated_sharpe)
+ ablation_results/overfitting_dashboard.md → E1.5 re-baseline the three champions.

GATE THRESHOLDS to encode: ship-to-shadow PBO<0.5; shadow-to-live PBO<0.2 AND DSR>0(95%) AND live-CLV.
Validation discipline: every change value-preserving; re-run champions through the new CV and report
the metric delta as the leakage estimate. Do NOT weaken evaluate_promotion's criteria 1-6.

COMPUTE (cost-first, §6): E1.3/E1.4 are embarrassingly parallel over folds/resamples → run as an
EC2/local BATCH job reading the training matrix as PARQUET from S3 (not repeated Snowflake scans);
cap CSCV partitions + bootstrap draws to bound cost; write reports/artifacts back to S3. These are
periodic, not daily.

Conventions: dbtf not dbt; Snowflake via MCP, fully-qualified, no USE; uv run python; hand >1min
scripts to the user; do not git commit/push.
```

### E1.6 — Cross-era run-environment regime weighting (soft)  ✅ **DONE 2026-06-18 — verdict: WASH** (history extension doesn't help; don't extend)  **[follow-on; enabled by E1.3]**

> **Build status (code + 16 tests green; full suite 206 pass):** `betting_ml/utils/run_env_regime.py` (cross-era profiler + per-game regime-similarity weight + canonical `regime_weight` column, drift-guarded), `load_features(min_year=…)`, gate wiring (`--regime-weight` × `--uniqueness-weight`, applied per-fold toward each eval season; `--min-year`), and the standalone profiler `betting_ml/scripts/regime/run_env_regime_profile.py` are written + unit-tested (incl. the real-data check that 2016 out-weights 2023/2019 — regime, not recency). Extending to `--min-year 2016` also gives the gate MORE eval folds (2019–2026).
> **AS-OF leakage check:** `feature_pregame_game_features` is ONE dbt model applied uniformly across all seasons, so pre-2021 rows use the SAME point-in-time AS-OF logic as 2021+ (not a separate era-specific backfill); the per-season coverage audit confirmed consistent population 2016+. The regime-weighted gate run is itself the empirical check — a leaky extension would degrade, not help.
> **Operator hand-off (Snowflake + minutes):**
> ```
> # 1) regime profile + per-season weights → ablation_results/run_env_regime_profile.md
> uv run python betting_ml/scripts/regime/run_env_regime_profile.py
> # 2) the re-eval: slim-14 totals on REGIME-WEIGHTED 2016+ history vs champion, purged CV
> uv run python betting_ml/scripts/promotion_gate_eval.py --target total_runs --purged-cv \
>   --regime-weight --min-year 2016 \
>   --challenger-contract betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_2026.json
> #    baseline to beat = the 2021-only slim-14 run (Δmae +0.0019); also watch the 2025-fold bias
> ```

**Why this exists (discovered 2026-06-17 during E1.3/E1.5):** training is floored at 2021 by `load_features` (`game_year >= 2021`), but the feature mart is populated back to **2015**, and the E1.3 prune showed the slim 14-feature totals model depends on features available back to **2016** (only `home_starter_stuff_plus` (2020, FanGraphs **hard** floor) and the two `home_team_sequential_*` posteriors (2021, an Epic-16 **backfill-scope** limit — source `stg_batter_pitches` goes to 2015) gate it, and all three are the *lowest*-importance signal features). So ~2× more history is available essentially for free.

**The catch (the real story):** "older = different run environment, so don't use it" is only half right — **run-environment regime is NOT time-ordered.** A 2-D regime read (scoring LEVEL + game-total SPREAD from `mart_game_results`) ranks **2016 (dist 0.35) and 2018 (0.64) as CLOSER to the current 2024–26 regime than 2023 (1.67, already trained on) or 2019 (3.88, peak juiced ball)**. A hard year cutoff therefore *admits* an off-regime season (2023) while *excluding* on-regime ones (2016, 2018). The fix is regime-similarity weighting, not a recency cutoff. The slim-14 calibration run (E1.3) also showed the residual totals over-bias is **+0.74 in 2025 alone** vs ≈+0.1 in 2024/2026 — i.e. regime lag, the exact thing this story targets.

**Tasks:**
- [x] **Cross-era regime profiler** (`betting_ml/utils/run_env_regime.py` + `scripts/regime/run_env_regime_profile.py`; distinct from the 2021+ within-series shift *detector* `run_env_regime_monitor.py`): per-season regime profile 2016–2026 on (a) scoring **level**, (b) game-total **spread/variance**, and (c) the **contact→runs conversion** axis (league offensive xwOBA — proxy from `home_off_xwoba_30d`/`away_off_xwoba_30d`, 2015+). Regime-distance per season from a trailing (default 2-season) current-regime centroid.
- [x] **Per-game regime-similarity weight** ∈ [MIN_WEIGHT, 1] (Gaussian kernel on the standardized regime distance), consumed through the **E1.2 `sample_weight` slot** — MULTIPLIES with `compute_sample_uniqueness` in `walk_forward_gate`. Canonical `regime_weight` column + drift-guard test (`test_run_env_regime.py`), mirroring `season_normalization`.
- [x] **`min_year` param on `load_features`** (default 2021; opt-in 2016). AS-OF leakage spot-check via architecture: one uniform dbt model across all seasons (not a separate backfill) + the coverage audit; the regime-weighted gate run is the empirical confirmation.
**AC:** re-run the **E1.3 slim-14 totals contract** on the **2016–2026 regime-weighted** set vs the champion under purged CV (E1.1). Regime weighting must (a) not regress accuracy/calibration vs the 2021+ slim model (`evaluate_promotion` + `--eval-calibration`), and ideally (b) reduce the 2025-driven pooled over-bias (+0.37). Report the per-season weights (expect **2019 ≈ 0.1×**, 2023 reduced; **2016/2018 ≈ full**). Keep Stuff+ dropped (hard 2020 floor); re-backfill the sequential posteriors to 2016 only if shown to matter (low importance → likely skip). **Soft-weight, not hard season-selection** (operator decision 2026-06-17).

```
▶ New-session prompt — Story E1.6 (cross-era regime weighting)

You are building Story E1.6 (cross-era run-environment regime weighting) of the MLB Edge Program.
GOAL: a regime-similarity SAMPLE WEIGHT so the slim totals model can train on 2016–2026 history
without naively pooling different run-environment regimes. SOFT-WEIGHT, not a hard year cutoff.

Context (read first):
  1. edge_program_implementation_guide.md §3 E1.6 (this story) + E1.2 (the sample_weight slot you reuse)
     + E1.3 (the 14-feature prune that motivates extending history)
  2. betting_ml/utils/sample_uniqueness.py (the E1.2 weight you MULTIPLY with) +
     betting_ml/utils/season_normalization.py (the parity-guarded canonical-column pattern to mirror)
  3. betting_ml/scripts/regime/run_env_regime_monitor.py (the EXISTING 2021+ shift detector — you build a
     SIBLING cross-era profiler, do not modify it) + feature_league_contact_baseline (the conversion axis)
  4. betting_ml/utils/data_loader.py::load_features (add a min_year param; default 2021)

KEY FINDING to encode: regime is NOT time-ordered — 2016/2018 are CLOSER to the current regime than
2023 (trained-on) or 2019 (peak juiced ball, exclude). Weight by regime distance, regardless of recency.

Build: cross-era regime profiler (level + spread + contact→runs conversion, per season 2016–26, distance
from a trailing current centroid) → per-game regime-similarity weight (Gaussian kernel) as a parity-guarded
column, multiplicable with the E1.2 uniqueness weight → load_features(min_year=2016) opt-in + AS-OF
leakage spot-check → re-gate the E1.3 slim-14 contract on the regime-weighted 2016–26 set vs champion
(purged CV + --eval-calibration); show per-season weights and the 2025-bias change.

Conventions: dbtf not dbt; Snowflake via MCP, fully-qualified, no USE; uv run python; hand >1min scripts
to the user; do not git commit/push.
```

### E1.7 — De-leak the production bullpen EB feature  ✅ **SHIPPED + VALIDATED 2026-06-18** (steps A–D; champion retrains = step E, gated post-E1.8)  **[⭐ Tier-0 correctness · touches the live champions · spun out of E2.1b]**

> **✅ Validated results (`E1_7_HANDOFF.md`):** **serving-null FIXED — 37/37 scheduled games populate `bp_eb_xwoba` (was 0); 96.9–98.9% historical coverage 2016–26.** Parity SQL↔Python ✅ (Jaccard 1.0, corr 0.962, mean|Δ| 0.0024). **MDA collapse confirmed on ALL THREE targets** — the leaky `bp_eb_xwoba` *value* → ~0% importance retained everywhere; **`bp_eb_coverage_pct` (data depth) rises to #1/#2 on all three** (uncertainty modest/variable). **Slim contracts re-derived (INTERIM — re-derive after E1.8):** total_runs 14→21, home_win 31→21, run_diff 19→15; **`elo_diff` + `pythagorean_win_exp_diff` newly enter both H2H contracts** — real team-strength signal the leak had masked. `bp_eb_xwoba` survives only on the home side of home_win/run_diff as a correlated *passenger* of `home_team_sequential_bullpen_xwoba` (E6.7 may legitimately drop it). **⚠️ dbt gotcha (captured so it won't recur):** `eb_bullpen_posteriors` is a thin ~12-day rolling incremental — a downstream-only `+` rebuild left history null + broke parity; the fix is DROP the 3 bullpen incrementals + full-refresh **including upstream** (`-s eb_bullpen_posteriors+`; `stg_batter_pitches` has all 12 seasons). **Promotion:** any contract must clear `promotion_gate_eval.py --purged-cv` before promotion — especially home_win (near-total 26-drop/16-add turnover). Step E (3 champion retrains) runs once on the post-E1.8 matrix.

> **⚙️ Weight choice (E1.7 build, 2026-06-18) — ✅ PM-ENDORSED: the dbt port uses EQUAL weight, not expected-leverage.** Equal ≈ expected to 0.001 per-side NLL (E2.1b), and the E2.1b handoff §4 explicitly recommends *"the simplest leakage-safe aggregate is the right replacement."* For a pure-SQL Path A port that matters doubly: porting the expected-leverage weighting (trailing-30d aLI from `delta_home_win_exp` + rest/fatigue availability multipliers) into dbt would be a large, error-prone *second* reimplementation — exactly the divergence risk the parity test exists to catch, amplified. Equal-weight is trivially correct, equivalent on NLL, and parity-checks cleanly against `aggregate_team_v3(weight_mode='equal')`. (Supersedes the "use expected" note below.)

**Why:** E2.1b proved `home/away_bp_eb_xwoba` — the #1/#2 feature on every champion — leaks. This column is in the **live home_win / run_diff / total_runs training matrices** → a **named mechanism for the offline→live skill collapse** (`[[project_prod_model_audit_jun2026]]`, offline corr 0.42 → live 0.001) previously filed broadly as "serving skew."

> **🔍 Refinement (E1.7 session, 2026-06-18) — it's TWO leaks, not one** (`eb_bullpen_team_posteriors.sql:33`): **(1)** the documented **weight** leak — `outs_in_game` weights each reliever's EB by the outs they recorded *in the game being predicted* (within-game peek); **(2)** an under-stated **roster/spine** leak — the table is built off `eb_bullpen_posteriors`, which only has rows for relievers who *actually pitched*, so it **only produces rows for completed games**. For tonight's scheduled slate there's **no row → `bp_eb_xwoba` is null/imputed at serve time.** That roster is both a leak (it encodes who pitched) *and* the **serving-null half of the offline→live collapse**. So the fix is not just "swap the weight" — it must **re-spine the feature onto the scheduled-game spine (`mart_game_spine`) with a leakage-safe trailing-30d pre-game pool** (exactly what `compute_bullpen_v3._load_expected_pen` already does). Per-reliever EBs stay as-of-safe; only **roster + weight** change. (Weight: **equal-weight shipped** — see the ⚙️ block above; equal ≈ expected to 0.001 NLL.) **✅ Serving-null fix verified: 37/37 scheduled games now populate `bp_eb_xwoba`.**

**PM decisions (2026-06-18):**
- **Standalone Tier-0 correctness card**, cross-linked to the Epic 30.3 serving-skew thread (same root, now with a mechanism). Correctness, not edge.
- **Implementation = Path A (port to dbt) + a parity guardrail.** Rewrite `eb_bullpen_team_posteriors.sql` to drive off `mart_game_spine` with the leakage-safe trailing-30d pool (equal/expected weight), column names unchanged → zero downstream churn, no new Python op in the incident-prone bullpen freshness chain, self-healing/incremental. **⚠️ The one risk Path A carries:** it re-implements the v3 pool/spine logic in SQL → a *second* implementation of the aggregate E2.1b validated in Python. **Add a SQL-vs-Python parity test** — the SQL port must reproduce `aggregate_team_v3`'s de-leaked values on the E2.1b eval folds — *before* the offline re-derivation/MDA is trusted. (Path B — repoint to the tested `eb_bullpen_team_posteriors_v3` table — is the fallback if we'd rather not maintain two implementations; it trades the parity burden for a Python producer in the daily chain.)
- **Retrain timing = batch ONCE after E1.7 + E1.8, on the fully de-leaked + leak-swept matrix.** ❌ **Retire the "pre-7M batch" trigger** (`[[project_model_retraining_deferral]]`) for this — **7M is a *legacy*-guide milestone and must not gate an Edge-Program correctness fix.** Rationale: **E1.8 (full leakage sweep) is queued next and will likely surface more leaks needing the same three ≥1hr NGBoost retrains** — retraining for E1.7 now and again post-E1.8 is a wasteful double ~3hr batch. So E1.7 **ships the SQL de-leak + matrix rebuild + MDA + the *prepared* retrain commands**, and the actual champion retrains ride **one batch after E1.8**. *(Guardrail: if E1.8 slips materially, retrain after E1.7 rather than leave leaked champions live indefinitely.)*

**Tasks:**
- [x] **Fix the construction (Path A):** re-spined `eb_bullpen_team_posteriors.sql` onto `mart_game_spine` with a leakage-safe trailing-30d pre-game pool (**equal** weight — see weight-choice note above); column names unchanged. `schema.yml` updated; `dbtf compile` clean (9/9). 2026-06-18.
- [x] **Parity test:** `betting_ml/scripts/eb_priors/parity_check_bullpen_deleak.py` — dbt table vs `aggregate_team_v3(weight_mode='equal')`: pool-membership Jaccard + xwoba corr/Δ (residual Δ = the leakage-safe EB-freshness gap). Operator-run (Snowflake).
- [ ] **Rebuild downstream** (operator; Snowflake >1min): ⚠️ **DROP + `--full-refresh`** (construction changed) → `eb_bullpen_team_posteriors+` rebuilds `mart_bullpen_effectiveness` → `feature_pregame_team_features` → `feature_pregame_game_features`; confirm `bp_eb_xwoba` is now **non-null for scheduled games** (the serving-null fix). See `E1_7_HANDOFF.md` §3.A.
- [ ] **Prepare (don't run) the 3 champion retrains** on the de-leaked matrix — staged in `E1_7_HANDOFF.md` §3.E for the post-E1.8 batch.
- [ ] **Re-derive the slim 14/31/19 contracts** on the de-leaked matrix → feeds E6.7 (`E1_7_HANDOFF.md` §3.D).
- [ ] **Complete the MDA collapse doc** on all three targets (`--bullpen-version v3` for `home_win` + `run_diff`; `total_runs` done) — `E1_7_HANDOFF.md` §3.C.
**AC + ⚠️ validation gotcha (critical):** the de-leaked feature **will look WORSE on offline NLL/Brier/importance — expected and correct** (you removed a peek); **NOT** a regression. Honest validation = **live/forward + the serving-parity harness** (does serve-time skill rise toward the now-honest offline number, AND does `bp_eb_xwoba` stop being null for scheduled games?), **never** offline metrics. Done (E1.7 scope) = leaky construction gone + re-spined onto the scheduled spine + parity test passes + downstream rebuilt + slim re-derived + MDA complete + retrain commands prepared; the **champion retrain + forward/parity gate completes in the post-E1.8 batch.**

```
▶ New-session prompt — Story E1.7 (de-leak the production bullpen feature)

You are building Story E1.7 of the MLB Edge Program — a Tier-0 CORRECTNESS fix. E2.1b proved the #1/#2
champion feature `bp_eb_xwoba` is a WITHIN-GAME LEAK (eb_bullpen_team_posteriors.sql weights reliever EB by
outs_in_game — outs recorded in the game being predicted). It feeds the LIVE champions → a named cause of the
offline→live collapse (0.42→0.001). This is correctness, not edge.

Read first: edge_program_implementation_guide.md §3 E1.7 + E2.1b + E2_1b_HANDOFF.md (the proof + the leakage-safe
machinery) + eb_bullpen_team_posteriors.sql + betting_ml/scripts/eb_priors/compute_bullpen_v3.py (aggregate_team_v3,
weight_mode equal/expected) + [[project_epic30_3_status]] (serving skew) + [[project_prod_model_audit_jun2026]].

Do: (1) replace the outs_in_game weight + appeared-in-game roster in eb_bullpen_team_posteriors.sql with a
leakage-safe aggregate (equal-weight or v3 expected-leverage — equivalent; reuse the E2.1b code); (2) re-train +
re-evaluate the home_win/run_diff/total_runs champions on the de-leaked matrix; (3) re-derive the slim 14/31/19
contracts on the de-leaked matrix (feeds E6.7); (4) run the --bullpen-version v3 MDA for home_win + run_diff to
finish documenting the collapse on all three targets.

⚠️ CRITICAL: offline NLL/Brier/importance WILL DROP — that is CORRECT (you removed a peek), NOT a regression.
Validate ONLY on live/forward + the serving-parity harness, never offline metrics. Conventions: dbtf not dbt;
Snowflake via MCP fully-qualified no USE; uv run python; hand >1min scripts to the operator; do not git commit/push.
```

### E1.8 — Full feature-surface leakage sweep  ✅ **AUDIT COMPLETE 2026-06-18** (2 leak-signature A/B confirmations staged for the operator)  **[⭐ high priority · gates trust in every offline number]**

> **✅ Verdict (`ablation_results/feature_leakage_audit.md`): the bullpen leak was the STANDOUT, not the tip of an iceberg.** Swept every signal-bearing + slim-contract feature across all 3 targets with the E2.1b 3-test template, tracing each to its dbt SQL. The construction surface is **essentially leak-free post-E1.7** — exactly **two** residual construction leaks, **both LOW-magnitude**: **(1) 🟥 FanGraphs Stuff+/arsenal block = LEAKY-season-to-date** (`feature_pregame_starter_features.sql:611` joins `season = year(game_date)` with no `< game_date` guard; `stg_fangraphs__stuff_plus` is grain pitcher×season at the *latest* ingestion → every historical game gets the full-season value, embedding game-G-and-later pitches). Magnitude is small (Stuff+ is a stable pitch-*shape* metric; #9 totals, noise on H2H) **but it hits 2 totals-slim-contract features** (`home_starter_stuff_plus`, `away_starter_avg_fastball_velo`) → **must de-leak before E1.9 trusts the totals contract.** **(2) 🟨 catcher framing/defense** = `LEAKY-blended-current-season` (70% weight on a latest-snapshot season total; noise-ranked, in no contract → low severity). **Everything else is AS-OF-SAFE:** the E1.7 bullpen fix is confirmed present in the live SQL; the Epic-16 sequential posteriors are safe because the *consumer* reads `prior_mu` (entering-G) / a strict `< game_date` as-of (the producer writes a through-G posterior, so this is a consumer-enforced barrier → §7.3 adds a dbt regression guard); standings/ELO/pythagorean (incl. the #3-on-totals `away_wins`), all team/pitcher rolling (inclusive windows repaired by `*_asof` carry-forward), base-state, lineup matchups (all prior-meeting/prior-season — no within-row peek), park, ump, injuries, OAA — all clean. **The H2H + run_diff slim contracts are FULLY CLEAN; only 2 of 57 slim slots (both totals/Stuff+) are leaky.** **Gap attribution:** the leaks do **not** explain the 0.42→0.001 collapse — the bullpen leak (now fixed) was the largest *named construction* slice; Stuff+/catcher are minor; the bulk of the live gap is **point-in-time serving skew** (lineup-dependent strong-tier null at morning serve), already on the Epic-30.3 track. ⏭️ **Operator:** §7.2 Stuff+ leak-signature A/B + MDA collapse (mirror `--bullpen-version v3`) → repoint prior-season **or** weekly-snapshot as-of → re-derive the totals slim contract **before** E1.9; §7.3 sequential-posterior dbt guards.

**Why (raised by the PM 2026-06-18):** the bullpen leak passed purged CV *and* was the single most important feature — if the program's #1 signal was a same-row peek, **other features may leak the same way**, and that could explain the broad **H2H + Totals offline→live collapse**, not just one feature. Purged CV is blind to this class (it guards temporal/cross-fold leakage, not a feature reading its own row). Until the surface is swept, **no offline number — including the E1 audit's own rankings and the slim-contract choice — is fully trustworthy.** This is the generalization of E1.7.

**Method (the E2.1b template, applied to the whole surface ~370 cols in `feature_pregame_game_features` + sub-model signals):**
- [ ] **Construction/source audit (primary):** trace each feature family's dbt/source lineage; flag any column that reads **game-G outcome or usage** (the `outs_in_game` pattern), post-game box/final stats, or anything **not knowable before first pitch**. Verdict per feature: as-of-safe / leaky / needs-PIT-proof. Prioritize the **top-N importance features per target + the slim 14/31/19 contracts** first (highest blast radius).
- [ ] **Serving-parity / offline↔live divergence test:** flag features that are **important offline but null/imputed/degraded at serve time** (reuse the serving-parity harness + the prod-audit data) — a high offline-importance feature that's absent live is the leak signature.
- [ ] **Leak-signature A/B + MDA collapse** where a leakage-safe reconstruction exists (as E2.1b did for bullpen): does importance survive a clean reconstruction?
- [ ] **Output:** `ablation_results/feature_leakage_audit.md` — per-feature verdict + a prioritized remediation list; each confirmed leak gets a de-leak fix (like E1.7) before any model that uses it is trusted/promoted.
**AC:** every top-importance feature + the slim-contract features carry a documented leakage verdict; confirmed leaks listed with a remediation owner; the audit explicitly reports **how much of the offline→live gap the found leaks explain.** ⚠️ Same gotcha as E1.7: removing leaks **lowers offline metrics by design** — validate honesty on forward/serving-parity, not offline.

```
▶ New-session prompt — Story E1.8 (full feature-surface leakage sweep)

You are building Story E1.8 of the MLB Edge Program — a systematic leakage audit of the ENTIRE feature surface.
Context: E2.1b found the #1/#2 champion feature (bp_eb_xwoba) is a within-game leak that purged CV missed
(it weights by outs_in_game — the eval game's own usage). The #1 feature leaking means others may too — this
sweep checks whether leakage explains the broad offline→live collapse (corr 0.42→0.001) across H2H + Totals.

Read first: edge_program_implementation_guide.md §3 E1.7 + E1.8 + E2_1b_HANDOFF.md (the 3-proof template) +
E1.3 clustered_feature_importance.py (the importance ranking to prioritize by) + the slim 14/31/19 contracts +
the serving-parity harness + [[project_prod_model_audit_jun2026]] + [[project_epic30_3_status]].

Do: (1) construction/source audit of every feature family — flag any column reading game-G outcome/usage or
otherwise not knowable before first pitch (the outs_in_game pattern); prioritize top-N-importance + slim-contract
features. (2) serving-parity test: flag features important offline but null/imputed/degraded live. (3) leak-signature
A/B + MDA collapse where a clean reconstruction exists. Write ablation_results/feature_leakage_audit.md with a
per-feature verdict + prioritized remediation list, and quantify how much of the offline→live gap the leaks explain.

⚠️ De-leaking lowers offline metrics BY DESIGN — that's correctness, not regression; judge on forward/serving-parity.
Conventions: dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run python; hand >1min scripts to the
operator; do not git commit/push.
```

### E1.9 — v6 clean-slate champion rebuild (model bake-off → Optuna)  ⬜  **[⭐ Model-A · this IS the post-E1.8 retrain — upgraded · needs E1.8 done]**

**Why (PM, 2026-06-18):** the champion retrains deferred by E1.7/E1.8 must **not** be a blind re-fit of the incumbent learner families. The current champions are **XGBoost for H2H (`home_win`) and NGBoost for totals (`total_runs`)** — historical defaults, never validated as best-in-class. Now that the matrix is being scrubbed of leakage (E1.7 + E1.8) and the contracts re-derived, **rebuild v6 from a clean slate: a "best model wins" bake-off across learner classes, decided by the honest gate, THEN Optuna hyper-parameter optimization on the winner** — not "tune the model we happened to start with." (Champions are currently `v5`; this produces **v6**.)

**Scope:** `home_win` (H2H) + `total_runs` (totals) — and `run_diff` on the same pattern — on the **final E1.8-clean matrix** with the **final re-derived slim contracts** (E1.7's are interim).

**Tasks:**
- [ ] **Model-class bake-off (selection BEFORE tuning):** evaluate a slate of candidate learners under **E1.1 purged CV** with each target's honest metric (H2H: NLL/Brier + calibration; totals: a **distributional** metric — CRPS/NLL — since totals needs a predictive distribution, not a point). Candidates: **XGBoost, LightGBM, CatBoost, NGBoost (distributional), a regularized GLM/logistic baseline, and a simple stack/ensemble** — plus the **no-skill + market baselines** as the floor. Market-blind (CONTRACT-GUARD). Pick the winner **by the gate metric + calibration**, not by incumbency or by a hair of NLL (ties → simpler/ more-calibrated/ distributional-where-needed wins).
- [ ] **THEN Optuna HPO on the winning class only** — purged-CV objective; **guard the HPO against its own overfitting** (the trial search is a multiple-testing surface): embargoed/nested CV for the objective, a sane trial cap, and **PBO<0.2 + DSR>0 (E1.4) on the selected config** so the tuned champion isn't a search artifact.
- [ ] **Promotion gate:** v6 must clear `promotion_gate_eval.py --purged-cv` (+ PBO/DSR) vs the v5 champion **on the clean matrix** before promotion; record the bake-off table (every class's CV score) + the chosen config in `ablation_results/`.
- [ ] Register `v6` in `sub_model_registry.yaml`; keep v5 until v6 clears live/forward.
**AC:** for each target, a recorded model-class bake-off (candidates × purged-CV metric) with a justified winner, an Optuna-tuned config that passes PBO/DSR, and a promotion-gate result vs v5 on the de-leaked+swept matrix. **⚠️ Honest validation:** offline scores are *lower* post-de-leak by design (not a regression); the trying-many-classes + HPO search is itself a multiple-testing surface → the **DSR/PBO discipline is the guard**, and the real proof is **forward/serving-parity**. **Downstream:** promoting v6 changes served picks for live beta users → coordinate the deploy with a `frontend/data/changelog.json` note. **Deps:** E1.8 (final clean matrix + final contracts); supersedes the bare "retrain" step of E1.7/E1.8.

```
▶ New-session prompt — Story E1.9 (v6 clean-slate champion rebuild)

You are building Story E1.9 of the MLB Edge Program — rebuilding the v6 champions (home_win, total_runs,
run_diff) from a CLEAN SLATE on the post-E1.8 de-leaked + leak-swept matrix. This is the deferred E1.7/E1.8
retrain, UPGRADED: do NOT blindly re-fit the incumbent classes (XGBoost h2h / NGBoost totals) — run a
"best model wins" bake-off, THEN Optuna-tune the winner.

Read first: edge_program_implementation_guide.md §3 E1.9 + E1.7 (the de-leak) + E1.8 (the sweep — its final
matrix + contracts) + E1.1 purged CV + E1.4 (PBO/DSR) + the current champion adapters (PlattCalibratedXGBClassifier,
the NGBoost totals model) + promotion_gate_eval.py + sub_model_registry.yaml.

Do: (1) MODEL-CLASS BAKE-OFF under E1.1 purged CV per target — XGBoost, LightGBM, CatBoost, NGBoost
(distributional), a regularized GLM/logistic baseline, a simple stack, + no-skill/market floors; H2H scored on
NLL/Brier+calibration, totals on a DISTRIBUTIONAL metric (CRPS/NLL — totals needs a distribution). Market-blind
(CONTRACT-GUARD). Winner by the gate metric + calibration, not incumbency. (2) Optuna HPO on the WINNER only —
purged-CV objective, embargoed/nested CV, trial cap, PBO<0.2 + DSR>0 on the selected config (the search is a
multiple-testing surface — guard it). (3) Promotion-gate v6 vs v5 on the clean matrix; record the bake-off table +
chosen config in ablation_results/; register v6, keep v5 until v6 clears live/forward.

⚠️ Offline scores are LOWER post-de-leak BY DESIGN — not a regression. The honest gate is forward/serving-parity +
PBO/DSR, never raw offline NLL. Promoting v6 shifts live picks → flag a changelog note for the app deploy.
Conventions: dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run python; hand >1min scripts (NGBoost/HPO
are long) to the operator; do not git commit/push. END with an ⏭️ Operator handoff (run-order + git add).
```

---

## 4. Epic E2 — Per-Side Generative Totals  ⬜  **[Track B-totals · the program's main edge bet — as an honest distribution/derivative *architecture*, not a single-feature signal (the bullpen signal was a leak; see E2.1b)]**

**Goal:** model home and away runs as correlated count distributions, convolve to an honest full predictive distribution, and price the **derivative markets books set lazily** (F5, team totals, alt-lines). Fixes the Story-29.1 variance deficiency and produces the user-facing distribution.

> **❌ RETRACTED (2026-06-18, E2.1b): the "bullpen EB dominates" finding was a leak.** E1.3 ranked `home/away_bp_eb_xwoba` #1/#2 on every target, and this note originally told E2 to "deepen the bullpen model" as the primary investment. **E2.1b proved that rank was a within-game leak** (the feature weights each reliever's EB by `outs_in_game` — the outs recorded in the game being predicted); de-leaked, its importance collapses to noise (0% retained). **So: there is NO "deepen the bullpen" investment in E2.** What remains true: (1) E2.1 should consume a **leakage-safe** bullpen aggregate (equal-weight ≈ v3), purely because the leaky one isn't computable live — not for lift; (2) the real action is the **production de-leak (E1.7)**; (3) the slim-14/31/19 re-promote must be **re-derived after the de-leak** (its ranking was contaminated). Full detail: `E2_1b_HANDOFF.md`.

**Build on what exists:** `offense_v2` (LightGBM+NegBin) already writes per-side `pred_runs_mu/dispersion/uncertainty` to `betting_features.offense_v2_signals`. E2 adds: calibration as a *bettable* distribution, the home/away dependence structure, convolution, and derivative pricing.

> **⛔ Market-blind constraint (architecture Principle 3 — non-negotiable).** The markets we're trying to beat already price in everything our baseball features contain. So **any model in this epic that is not itself modeling market behavior MUST be market-blind**: no odds, implied probabilities, line-movement, consensus, or book features in its inputs (E2.1–E2.5). A totals model that trains on the line just *relearns the line* (circularity/leakage) and can add nothing orthogonal — which is exactly why the current stack can't beat the market. Market data enters **only** at the evaluation/CLV-gating layer (E2.6) and in the separate market models (E3/E4). The historical derivative odds from E2.0 are used **for scoring/CLV only — never as model features.** A `CONTRACT-GUARD`-style assertion must confirm zero market columns reach the E2 feature matrix. (Same rule binds E5–E8; it's restated here because totals is where the market-leakage temptation is strongest.)

> **🔢 Sequencing (gating dependency).** The **derivative-odds backfill (E2.0)** — historical F5 / team-total / alt-total closing lines — **must be complete before E2.6** can validate the derivative edge: you cannot gate "beats the derivative's own close" without the historical closes. E2.0 is market-data plumbing (Session B; shares the E5.0/E5.1 Odds-API event-odds ingestion), runs **in parallel with** the market-blind model build (E2.1–E2.5), but **blocks the totality of the epic at the E2.6 gate.** Start it early so it isn't the long pole.

### E2.0 — Derivative-odds backfill (gating dependency)  ✅ **SHIPPED 2026-06-18**  **[Track data / Session B · unblocks E2.6]**
> **✅ Result:** `scripts/derivative_odds_backfill.py` → `oddsapi.derivative_odds_raw` (idempotent via `fetch_status` sentinels — sentinel'd events are skipped, no wasted credits) → `stg_derivative_odds` → **`mart_derivative_closes`** (grain `game_pk × market_key × bookmaker_key × outcome_name`; "close" = last pre-game snapshot with `actual_snapshot_ts ≤ commence_time` leakage guard; INNER-join to `mart_game_odds_bridge`). **238,421 closes / 5,896 games · 2023-05-03→2026-06-06 · 24 books · zero leakage violations · implied-prob 0.029–0.990 (avg 0.532).** Full dbt tests pass. **EVAL/CLV-ONLY** (Principle 3 — never a training feature). Markets: team_totals, alternate_totals, h2h_h1, totals_h1.
> **⚠️ Two gaps → E2.0b (live capture follow-on):** **(1) F5 historical is sparse — only ~65 games, all 2023** (the Odds API historical endpoint didn't offer F5 consistently) → **the F5 derivative edge cannot be backtested from history; validating the F5 "softer market" thesis needs *forward* capture.** **(2)** Latest game is 2026-06-06 → ongoing games need a **live capture cadence.** Both are E2.0b.
> **dbt-test fix (E9.2 session, 2026-06-18):** removed the `not_null` test on `raw_json` in the `derivative_odds_raw` source — **sentinel rows are NULL by design** (idempotency records for failed/empty API fetches; the staging model filters them with `WHERE raw_json IS NOT NULL`). The test was a false CI failure; the sentinel design is correct.

**Tasks (as built):**
- [ ] Backfill historical **derivative totals lines** — first-5-innings (F5) totals, team totals, and alternate game totals — via The Odds API **historical event-odds** (`10 × markets × regions`/event/snapshot; additional-market history only after **2023-05-03**; use GET historical events for eventIds). Reuse the E5.0/E5.1 prop-ingestion pattern (Railway cron / batch; raw → staging).
- [ ] **Closing snapshot per game** first (the CLV reference); optional open snapshot for movement. Leakage-safe snapshot timestamps. Bovada + curated soft books + Pinnacle (sharp reference).
- [ ] Land in a `game_pk`-keyed mart so E2.6 can join model distribution → derivative line → realized outcome. **Eval/CLV use ONLY — never joined into the E2 model feature matrix** (market-blind constraint, above).
**AC:** game×market historical derivative-totals lines (F5 / team-total / alt-total), close (+ open where available), 2023-05-03 → present; coverage report; credit spend logged (same order as the E5.1 prop backfill — comfortably inside 5M/mo).

### E2.0b — Live derivative-odds capture (forward cadence)  ✅ **SHIPPED 2026-06-18**  **[Track data / Session B · E2.0 follow-on]**
> **✅ Result:** `scripts/derivative_odds_backfill.py` gained `probe` (Event Markets / Schema-6 recon) + `capture` (forward cron runner, reads `DERIVATIVE_CAPTURE_MARKETS`); **`services/derivative_capture/`** = a Railway cron (`*/30 * * * *`, restartPolicy NEVER) capturing live → `derivative_odds_raw` via the E2.0 two-phase bulk-load. **Live for `team_totals,alternate_totals`.**
> **🔴 PROBE FINDING (5 events, 2026-06-18) — F5 is unavailable, not just thin:** **`h2h_h1`/`totals_h1` offered by ZERO bookmakers** via The Odds API (live). `team_totals` = betmgm/bovada/draftkings/pinnacle; `alternate_totals` = all 5; update cadence ~30 min. So **forward-F5 capture is blocked at the source** — the historical 65-game sparsity is *ongoing*, not a backfill quirk. → **F5 needs a different data source (E2.0c)** or the F5 thesis dies. The probe paid for itself: it killed a doomed pipeline build before it started.
**Why (from E2.0, 2026-06-18):** the backfill only ran to 2026-06-06, and **F5 historical is too thin to backtest (~65 games, all 2023).** So we needed an ongoing capture that keeps `mart_derivative_closes` current; F5 forward-capture *would* have been the path — but the probe found F5 isn't offered at all (above).
**Tasks:**
- [ ] **PROBE FIRST (cheap recon — do before building the cadence; operator idea 2026-06-18):** query the **Event Markets** endpoint — `GET /v4/sports/baseball_mlb/events/{eventId}/markets` (Odds API v4 "Schema 6"; returns each bookmaker's available markets **+ a per-market `last_update`, without the odds payload** → cheap) — for a sample of upcoming MLB events across the curated books. Use it to answer two things before committing a cadence: **(1) Are the derivative markets actually offered live right now — especially F5 (`h2h_h1`/`totals_h1`)?** If F5 isn't in the markets list, **forward-F5 capture is blocked too** (the historical sparsity is ongoing) — a cheap kill/confirm signal that decides whether E2.4's F5 thesis is alive at all. **(2) How often do the derivative markets actually move?** The per-market `last_update` timestamps reveal each derivative market's real update cadence → **size the capture cadence to match** (don't poll faster than the markets change; saves credits).
- [ ] A **scheduled capture** of the (confirmed-available) derivative markets (team_totals, alternate_totals, and F5 h2h_h1/totals_h1 **if the probe shows they're offered**) for the upcoming/in-progress slate — mirror the **A2.18 Railway odds-capture cron** (flat-cost cron, not per-snapshot Dagster), reusing `derivative_odds_backfill.py`'s idempotent sentinel pattern, at the **probe-derived cadence**. Snapshot near close; land into the same `derivative_odds_raw` → `mart_derivative_closes` path.
- [ ] **Credit guard** + cadence tuned to the slate (capture only scheduled games; log spend vs the 5M/mo budget).
- [ ] **EVAL/CLV-ONLY** (Principle 3) — never a training feature.
**AC:** the **probe report** is recorded first (which derivative markets are live-offered — esp. F5 yes/no — and each market's observed update cadence from `last_update`); the capture cadence is **sized from the probe**; `mart_derivative_closes` stays current for live games (no multi-day lag); forward F5 closes accumulate **if F5 is offered** (else F5 is recorded as not-live-available → flag to E2.4); credit spend logged. **Deps:** E2.0 (the pipeline it extends), A2.18 (the cron pattern). Pairs with E5.0 (live prop capture — same plumbing).

```
▶ Story prompt — E2.0b Live derivative-odds capture (forward cadence)   [Model-B · data · E2.0 follow-on]
Read: §4 E2.0 + E2.0b + §0 + §6 + scripts/derivative_odds_backfill.py (the pipeline you extend) + A2.18 (services/odds_capture cron pattern) + E5.0 (parallel live prop capture).
Do: schedule a forward capture of the 4 derivative markets for the upcoming/in-progress slate (mirror the A2.18 Railway cron, reuse the idempotent sentinel pattern), snapshot near close → derivative_odds_raw → stg_derivative_odds → mart_derivative_closes. Credit-guard to scheduled games + log spend. Especially accumulate forward F5 (h2h_h1/totals_h1) closes — history is too thin (~65 games, 2023) to backtest F5, so forward is the only path. EVAL/CLV-ONLY (never a model feature; CONTRACT discipline).
Gate/AC: mart_derivative_closes stays current for live games; forward F5 closes accumulate; credit logged; EVAL/CLV-only.
Closeout (per §0.1): END with an ⏭️ Operator handoff — run-order (incl. the cron deploy), git add, what to verify (new closes land for today's slate).
```

### E2.0c — Alternative derivative-odds data source (F5 + coverage)  ✅ **RESEARCH DONE → 🅿️ DEFERRED (operator 2026-06-18): SportsGameOdds, but buy post-100-users + post-cost-opt**  **[Track data / Session B · research]**
> **✅ Survey result (`docs/e2_0c_f5_source_survey.md`, adversarially verified):** F5 is **scarce across the whole market**, not just our source. **SportsGameOdds** is the *only* provider that explicitly documents F5 — but it's **deprecating `1ix5`→`1h`**, history is **Pro-tier only ($299/mo = ~2× our current ~$150–200 spend)**, and its JSON is structurally inverted (needs an ETL shim, not a drop-in). **OddsJam** = F5 unverifiable from public docs (contact-only pricing). **OpticOdds / Sportradar / Genius** = enterprise ($2.5–5k+/mo, priced out). Scraping sources = not production-grade. **Verdict: PAUSE — two sales inquiries decide it.**
> **✅ DECISION (operator, 2026-06-18): chosen source = SportsGameOdds — but DEFERRED (paid), not bought now.** Verified current pricing (`sportsgameodds.com/pricing`, Jun 2026): **Pro $299/mo** (UNLIMITED objects, sub-min updates, 53 leagues, **82 books incl. Pinnacle + Fanatics**, **Partials/"1st half" ✓**, **Historical data ✓**); **Rookie $99/mo** (Partials ✓ but **NO history**); **Amateur = FREE** (2.5k objects/mo, 9 books, 8 leagues, **Partials ✓**); **annual billing ≈ −40% → Pro ~$179/mo effective**. **Buy the *paid* plan AFTER (a) the ~100-paying-user / revenue milestone (`../gtm_strategy.md`) AND (b) the Snowflake/Dagster cost-optimization items (E11) land** — cost savings free the budget. F5 is therefore **PARKED (not killed)** behind those two gates.
> **🆓 FREE-TIER VALIDATION FIRST (operator idea 2026-06-18 — can do anytime, $0):** before committing a cent, sign up for the **free Amateur tier** and use it to **confirm MLB `1h` actually returns first-5-innings markets** (resolve the `1ix5→1h` question definitively), **capture the JSON shape**, and **build/test the ETL shim** into `derivative_odds_raw` → `mart_derivative_closes`. This de-risks the whole purchase — you'll *know* F5 works for MLB and have the integration ready — for free, and it isn't gated by the revenue/cost-opt milestones (only the paid Pro commitment is). The free tier has **no history + low volume**, so it can't backtest — but it's perfect to validate *availability + format* (the actual open question).
> **💡 Re-evaluate at purchase: additive vs replacement.** At **annual ~$179/mo** with **82 books + Pinnacle + Fanatics + props + partials + history**, SportsGameOdds Pro could **replace The Odds API (~$150-200/mo)** rather than be a *second* bill — changing the cost case from "2× spend for F5" to "comparable spend, more coverage + F5." Evaluate consolidation (one provider) at decision time, not just additive F5.
> **⏭️ Still pending — OddsJam inquiry** (operator emailed 2026-06-18): do you carry `h2h_h1`/`totals_h1`? history depth? price? — could change the chosen source if it beats SportsGameOdds on F5/history/price.
> **🔪 Residual kill option:** if at purchase time SportsGameOdds `1h` ≠ MLB F5, OR Pro history doesn't reach ≥2021, OR the economics don't work post-cost-opt → **kill F5** (strip its gate from E2.4 + E2.6; lean on team/alt totals).

**Why:** the E2.0b probe found **The Odds API offers no F5 (`h2h_h1`/`totals_h1`) for MLB at all** (live *or* historical beyond 65 games), and only 4–5 books for team/alt totals. The totals-derivative value path (E2) — especially the **F5 "softer market" thesis (E2.4)** — depends on having these lines. **Operator directive:** if a market we want isn't well-covered by our current source, **find a reliable source that has it.** This story surveys and secures one.
**Tasks:**
- [ ] **Survey candidate sources** for MLB derivative odds — esp. **F5/first-5-innings** lines, and deeper `team_totals`/`alt_totals` book coverage. Candidates to evaluate: **OddsJam**, **SportsGameOdds**, other aggregators, direct sportsbook feeds/apps that publish F5 (some books carry first-5 lines that the Odds API aggregation simply doesn't surface). 
- [ ] **Evaluate each on:** (1) **F5 coverage** (do they actually carry h2h_h1/totals_h1, and for how many books?); (2) **history depth** (can we backtest, or forward-only?); (3) **cost** vs the current 5M-credit Odds API budget; (4) **reliability + ToS/legality** (scraping vs licensed API); (5) integration fit (can it land in the existing `derivative_odds_raw` → `mart_derivative_closes` path?).
- [ ] **Recommendation + integration path** for the chosen source (or "none viable"). EVAL/CLV-ONLY constraint carries.
**AC:** a written source-comparison + a recommendation (`ablation_results/` or a short doc); **a decision on F5** — either a secured source (with integration plan) or a formal **kill of the F5 thesis** (→ update E2.4/E2.6, lean the derivative path on team/alt totals). **Deps:** E2.0/E2.0b (the pipeline a new source would feed). **Note:** Pinnacle is already reachable via the Odds API `eu` region; this is about *markets* (F5) the aggregator doesn't carry, not just books.

```
▶ Story prompt — E2.0c Alternative derivative-odds data source (F5 + coverage)   [Model-B · data · research]
Read: §4 E2.0/E2.0b/E2.0c + the E2.0b probe finding (Odds API offers NO F5; team/alt = 4–5 books) + §6 (cost) + scripts/derivative_odds_backfill.py (the path a new source would feed).
Do: survey + evaluate candidate MLB derivative-odds sources (OddsJam, SportsGameOdds, direct book feeds, others) for: F5 (h2h_h1/totals_h1) coverage + book count; history depth (backtestable vs forward-only); cost vs the 5M-credit Odds API budget; reliability + ToS/legality; integration fit into derivative_odds_raw → mart_derivative_closes. Produce a comparison + recommendation.
Gate/AC: source-comparison doc + a recommendation; an explicit F5 decision — secure a source (with integration plan) OR formally KILL the F5 thesis and update E2.4/E2.6. EVAL/CLV-only carries.
Closeout (per §0.1): END with an ⏭️ Operator handoff (the doc + any spike code + git add). No live integration in this story unless a source is chosen — that's a follow-on.
```

### E2.1 — Per-side count-distribution model  ✅ **GATE PASS 2026-06-18**  **[market-blind]**
> **Result:** NegBin beats Poisson on per-side-runs NLL (5/5 purged-CV folds, +0.093 mean), overdispersion recovered (var/mean≈1.6, `r` 8–33 across folds), market-leakage guard clean (0 market cols / 282 feats). Artifact `totals_perside_v1.pkl` + CV record `e2_1_perside_negbin_cv.json` written; **correctly NOT promoted to S3** (gated at E2.6). This marginal is what E2.1b/E2.2/E2.3/E2.5/E2.6 build on. (Two downstream notes folded into E2.2.)
**Tasks:**
- [ ] Per game/side **NegBin** runs distribution (`sub_model_output_standard` mandates NegBin for per-side counts; var/mean=2.26 justifies the overdispersion). Emit `mu`, `dispersion`, `uncertainty` per side.
- [ ] Inputs (**baseball/context only — no market features**): that side's offense (`feature_pregame_lineup_features`; `feature_pregame_expected_lineup` pre-lineup), opposing starter (`feature_pregame_starter_features`, `eb_starter_posteriors`), opposing bullpen (`eb_bullpen_team_posteriors`), park/env (`feature_pregame_park_features`, `run_env_v4`, `feature_league_contact_baseline`), weather, umpire.
- [ ] Build on `offense_v2`'s existing per-side NegBin rather than from scratch; document what E2.1 changes vs `offense_v2` (calibration target, added inputs).
- [ ] **CONTRACT-GUARD:** assert zero market/odds columns in the training matrix.
**AC:** per-side NegBin beats a Poisson baseline on held-out per-side-runs NLL under E1.1 purged CV; overdispersion recovered; market-leakage guard passes.

**🔄 CODE-COMPLETE (2026-06-18) — pending operator gate run.** Built `betting_ml/scripts/totals_generative/train_perside_negbin.py`: unpivots the wide per-game mart `feature_pregame_game_features` into one row per (game_pk, side) — `off_*` = batting side, `opp_*` = the opposing starter/bullpen/staff/catcher, plus shared park/env/weather/umpire — and fits a count-natural LightGBM Poisson-loss mean + MLE NegBin `r`, scored under **E1.1 `PurgedWalkForwardSplit`** against an explicit Poisson baseline (gate = NegBin NLL < Poisson NLL & var/mean>1). The market-blind CONTRACT-GUARD is the reusable `betting_ml/utils/market_blind.py` (`assert_market_blind`, binds E2/E5/E6/E7/E8); tests `betting_ml/tests/test_market_blind.py` + `test_perside_assembly.py` (70 passing). Documented deltas vs `offense_v2`: (1) full opposing-pitching + park/weather/ump inputs (offense_v2 saw only the batting side), (2) purged CV, (3) Poisson-loss mean + explicit Poisson baseline. **Operator:** `uv run python betting_ml/scripts/totals_generative/train_perside_negbin.py` (>1-min Snowflake + multi-fold LightGBM). Writes artifact `models/sub_models/totals_perside_v1/` + CV record `ablation_results/e2_1_perside_negbin_cv.json`; NOT promoted to S3 (gated at E2.6). Feeds E2.2 (copula) as the NegBin marginal; signal registration is E2.5.

### E2.1b — Bullpen model deepening (`bullpen_v3`)  ✅ **COMPLETE 2026-06-18 — GATE FAIL by design (the failure is the finding)**  **[market-blind]**

> **⚠️ READ THE VERDICT BLOCK BELOW FIRST.** The original premise of this story (everything in **Why** + the design-fork notes below) — *"bullpen EB is the #1/#2 signal, deepen it as E2's primary investment"* — was **disproved by this story's own execution: that #1/#2 rank was a within-game leak.** The text below is kept as the as-written brief for provenance; the **✅ COMPLETE** block is the real outcome. Net: there is no "deepen the bullpen" investment; the action is the **de-leak (E1.7)**.

**Why (as originally written — now superseded, see verdict):** the E1 audit (2026-06-18) ranked **bullpen EB quality (`home/away_bp_eb_xwoba`) #1/#2 on *every* target** — the single clearest "more modeling pays here" finding the program has. Today the per-side model consumes `eb_bullpen_team_posteriors` as a **static team-level EB shrink**; it ignores *who is actually available tonight* and *what state the pen is in*. This story makes the bullpen input richer and game-specific. It is the **primary modeling investment inside E2** and the one feature direction E6's "more features ≠ edge" conclusion explicitly exempts.

> **⭐⭐ LEAKAGE FINDING (build session, 2026-06-18) — the core of `bullpen_v3`.** The static team EB aggregates per-reliever posteriors **weighted by `outs_in_game`** — the outs each reliever *actually recorded that night*. The EB **values** are as-of-safe, but the **weights use tonight's realized usage, which is unknown pre-game** → the program's #1 feature is built on a **subtly leaky weighting.** Replacing those weights with **expected leverage × availability** (per-reliever aLI from `int_bullpen_ali_by_season` × `mart_reliever_top3_availability`) is simultaneously the "composition-weighted EB" ask **and a genuine leakage fix.** This is the heart of the story.
> - **Honest re-measure required:** because E1's dominant feature was partly leaky, **re-run the E1.3 clustered-MDA after the fix** and report honestly whether bullpen EB's importance *drops* once the leak is removed. If it does, that's a real, welcome update to the E1 conclusion — we want to know. (It does **not** invalidate E2.1's NegBin-beats-Poisson gate — that's distribution shape — but any go-live use of the bullpen input should be on the fixed version.)

> **Design decisions (2026-06-18) — recommended resolution of the build-session forks:**
> - **Build on the existing marts, don't duplicate:** `mart_bullpen_workload` / `mart_reliever_top3_availability` / `mart_bullpen_leverage` / `mart_bullpen_handedness_splits` / `feature_pregame_bullpen_state_features` (fatigue/availability/leverage/L-R) + `int_bullpen_ali_by_season` (the expected-leverage weight) already exist — `bullpen_v3` assembles from these, it does not re-derive them. Staged build (compute → EB-hierarchy refit → CV gate vs static EB → clustered-MDA re-check → register + leakage-safe backfill) is endorsed.
> - **Platoon-split fork → ship (a) as the gated baseline; let (b) earn its place.** (a) composition-weight the existing **team** L/R xwOBA (`mart_bullpen_handedness_splits`) by the available-pen composition — leakage-safe, reuses what exists, ships a real available-pen L/R input now. (b) full per-reliever × LHB/RHB EB is more principled **but** splits each reliever's already-thin sample in half → heavy shrinkage likely **collapses (b) back toward (a)** anyway, at materially higher build/compute/leakage surface. That's exactly the over-parameterization E1 just flagged. **So: build (a) first as the baseline; build (b) only if it *beats (a)* on held-out per-side-runs NLL under E1.1 purged CV.** "Best product" = the version *validated* to be better, not the most elaborate — and this way we likely get the principled answer for free, or a measured reason to pay for (b). Whichever wins must be as-of-safe + market-blind.

**Tasks:**
- [ ] **Pen-state features (the highest-leverage add):** opposing-bullpen **availability/fatigue** as-of first pitch — back-to-back usage, pitches/appearances over a trailing window, days rest per reliever, projected-unavailable arms — rolled to a team-game **available-pen** aggregate. Source from `mart_pitch_play_event` / appearance logs; strictly as-of (no same-game leakage).
- [ ] **Composition-weighted EB:** instead of a flat team posterior, weight reliever EB posteriors by **expected leverage/innings tonight** (closer/high-leverage arms weighted up), so the input reflects the pen likely to actually pitch, not the season-average roster.
- [ ] **Handedness / platoon split:** carry the available pen's L/R EB split so E2.1 / E6.3's platoon×bullpen interaction has a real input.
- [ ] **Reliever-level shrinkage review:** re-fit the bullpen EB hierarchy (per-reliever → team → league) and check the `k`/shrinkage choice with purged CV — the dominant feature deserves a deliberately-fit prior, not an inherited default.
- [ ] Emit a versioned `bullpen_v3` posterior/feature set to the signal mart (mirror `offense_v2_signals`; register in `sub_model_registry.yaml`); leakage-safe backfill per `[[project_layer3_signal_leakage]]`.
- [ ] **CONTRACT-GUARD:** zero market/odds columns (market-blind).

**AC:** `bullpen_v3` available-pen + composition-weighted EB + platoon split populated and leakage-safe; **measured improvement vs the static team EB on per-side-runs NLL under E1.1 purged CV** (the bar is *beat the current bullpen input*, not the no-skill floor); feeds E2.1 as a drop-in richer input; importance re-checked via E1.3 clustered MDA (does the deepened bullpen signal stay #1, and does pen-state add over static EB?). **Honest framing:** a measured-lift investment in the proven-dominant signal — not a presumed edge.

**✅ COMPLETE (2026-06-18) — GATE FAIL by design; the failure IS the finding.** The story asked "does deepening the bullpen model beat the current input on per-side NLL?" Measured answer: **NO — because the "current input" was never pre-game skill, it was a within-game leak.** Verified three ways: (1) **NLL leak-signature** — leakage-safe equal-weight (2.4582) and v3 (2.4571) land within 0.001 of each other and both lose to leaky-static (2.4303) by an identical ~0.027 ⇒ the gap is the peek, not v3 being worse; (2) the **dbt model** `eb_bullpen_team_posteriors.sql:33` weights per-reliever EB by `outs_in_game` over the roster of arms that *actually pitched the eval game* (a within-game peek purged CV can't catch); (3) the **MDA re-check** (`--bullpen-version v3`, total_runs) collapses `home/away_bp_eb_xwoba` from rank #1/#2 (imp +0.078/+0.065) to **noise** (rank 40/39, imp +0.0002/+0.0003, CI crosses 0) — **0% importance retained**. Only `bp_eb_uncertainty` (~28%) + `bp_eb_coverage_pct` (rises to #1–2 de-leaked) carry real pre-game bullpen signal — data-depth, not the xwOBA value. **Implications:** E1.3's "bullpen EB dominates every target" headline is leak-inflated; and since this feature feeds the live home_win/run_diff/total_runs training matrices, it is a named mechanism for the offline→live skill collapse ([[project_prod_model_audit_jun2026]], corr 0.42→0.001). v3's leverage/availability weighting is **neutral** vs plain equal-weight (0.001) → the simplest leakage-safe aggregate is the right replacement; **do NOT build Experiment B** (no measured headroom — multiple-testing trap). **Spin-off card recommended: de-leak the production feature** (swap `outs_in_game` → leakage-safe weight in the dbt model) + re-evaluate the base champions. Full write-up: `E2_1b_HANDOFF.md`.

**Build (the leakage-safe machinery — reusable for the de-leak fix).** The static `eb_bullpen_team_posteriors` aggregates per-reliever EB **weighted by `outs_in_game` = the outs each reliever actually recorded that night** — as-of-safe EB values but a *leaky weighting* (tonight's usage is unknown pre-game). `bullpen_v3` replaces those weights with an **expected** composition weight `w_i = expected_leverage_i (trailing-30d aLI, as-of) × availability_i(rest, fatigue)` — projected-unavailable (back-to-back / heavy-use) arms down-weighted, not dropped. The leak fix **is** the composition weighting (locked design decision). Platoon channel (a) = the leakage-safe team L/R split (`mart_bullpen_handedness_splits`) carried onto the v3 row; per-reliever×handedness EB (b) is a **gated** follow-up that must beat (a) — not pre-committed.
- **`betting_ml/scripts/eb_priors/compute_bullpen_v3.py`** — heavy Snowflake query ONCE → per-reliever cache (parquet, `models/sub_models/bullpen_v3/`); pure-Python `aggregate_team_v3(cache, k)` forms the team posterior at any shrinkage `k` (no re-query); writes `baseball_data.betting.eb_bullpen_team_posteriors_v3` (game_pk × team) via MERGE; CONTRACT-GUARD (`assert_market_blind`) on the output columns.
- **`betting_ml/scripts/totals_generative/eval_bullpen_v3_cv.py`** — the E2.1b gate: an A/B that holds the E2.1 per-side surface fixed and swaps only the bullpen channel — **BASELINE** (static, leaky weight) vs **V3-LEAKFIX** (expected-weight, same column slot → isolates the fix) vs **V3-PENSTATE** (+ platoon + availability channels → does pen-state add). Reports per-side NegBin NLL per fold under `PurgedWalkForwardSplit` + a shrinkage-`k` sweep. Gate PASS ⇔ V3-LEAKFIX mean NLL < static at the chosen `k`.
- **`clustered_feature_importance.py --bullpen-version v3 --shrinkage-k <k>`** — the REQUIRED honest MDA re-check: swaps the v3 column in, writes `*_bullpen_v3` outputs, so we report whether `bp_eb_xwoba` importance DROPS once the leaky weighting is gone (≠ a presumed-stays-#1).
- Registered `bullpen_v3` in `sub_model_registry.yaml` (status `pending` → `challenger` on gate pass); tests `betting_ml/tests/test_bullpen_v3.py` (14 passing: EB-`k` math/parity, availability down-weight, leverage-weighting, platoon carry, market-blind guard).

**Operator runbook (>1-min Snowflake jobs; one `--backfill-season` per invocation, parallelizable):**
```bash
# 1. heavy: per-reliever cache per honest-OOS season (run in parallel)
uv run python betting_ml/scripts/eb_priors/compute_bullpen_v3.py --backfill-season 2021
uv run python betting_ml/scripts/eb_priors/compute_bullpen_v3.py --backfill-season 2022   # …2023 2024 2025 2026
# 2. gate + shrinkage-k sweep (static vs v3 on per-side NegBin NLL, purged CV)
uv run python betting_ml/scripts/totals_generative/eval_bullpen_v3_cv.py --min-year 2021 --k-sweep 0.5 1.0 2.0 4.0
# 3. if PASS: materialise the team table at the chosen k (per season)
uv run python betting_ml/scripts/eb_priors/compute_bullpen_v3.py --backfill-season 2021 --shrinkage-k <k> --write   # …each season
# 4. REQUIRED honesty check — does bp_eb_xwoba importance drop once the leak is gone?
uv run python betting_ml/scripts/clustered_feature_importance.py --target home_win   --bullpen-version v3 --shrinkage-k <k>
uv run python betting_ml/scripts/clustered_feature_importance.py --target run_diff   --bullpen-version v3 --shrinkage-k <k>
uv run python betting_ml/scripts/clustered_feature_importance.py --target total_runs --bullpen-version v3 --shrinkage-k <k>
```
**Post-gate wiring:** once the table is live, E2.1's `load_wide` consumes `bp_eb_xwoba` from `eb_bullpen_team_posteriors_v3` (drop-in); a dbt model surfacing the v3 columns into `feature_pregame_game_features` is the daily-serve path (E2.5 backfill registers the signal).

```
▶ New-session prompt — Story E2.1b (bullpen model deepening / bullpen_v3)

You are building Story E2.1b of the MLB Edge Program — deepening the bullpen model, which the E1 audit
(2026-06-18) found is the #1/#2 feature on EVERY target (home_win / run_diff / total_runs). This is the
program's clearest signal-investment direction. It feeds E2.1 (per-side totals) as a richer drop-in input.

Read first:
  1. edge_program_implementation_guide.md — Epic E2 (§4), esp. E2.1 + E2.1b + the ⭐ E1 finding + §0 + §6 cost
  2. the E1.3 clustered-feature-importance output (the cross-target ranking that put bullpen EB #1/#2)
  3. eb_bullpen_team_posteriors + the EB-posterior fitting code (the static team shrink you are replacing)
  4. mart_pitch_play_event / reliever appearance logs (the pen-state / fatigue source) + sub_model_registry.yaml

Build (MARKET-BLIND — CONTRACT-GUARD that no odds/line/consensus columns enter the matrix):
  - pen-state / availability+fatigue features as-of first pitch (back-to-back, trailing pitches/appearances,
    days rest, projected-unavailable arms) → team-game available-pen aggregate;
  - composition-weighted EB (weight reliever posteriors by expected leverage/innings tonight, not season avg);
  - L/R platoon EB split of the available pen;
  - re-fit the per-reliever→team→league EB hierarchy; justify k/shrinkage under purged CV.
Emit a versioned bullpen_v3 signal (mirror offense_v2_signals; register in sub_model_registry.yaml);
LEAKAGE-SAFE backfill (project_layer3_signal_leakage). Gate: beat the STATIC team EB on per-side-runs NLL
under E1.1 purged CV; re-run E1.3 clustered MDA to confirm the deepened signal stays dominant + pen-state adds.

COMPUTE (§6): appearance/pitch rollups are heavy → S3-Parquet/DuckDB or EC2 batch, periodic not daily;
daily Dagster op only scores the upcoming slate's available-pen state. Conventions: dbtf not dbt; Snowflake
via MCP fully-qualified no USE; uv run python; hand >1min scripts to the operator; do not git commit/push.
```

### E2.2 — Dependence structure (copula)  ✅  **[market-blind · finding: copula UNNECESSARY; the gap is marginal dispersion]**
> **✅ GATE RAN 2026-06-22 — honest finding (NOT-MET = the finding, like E2.1b).** `betting_ml/utils/copula.py` + `betting_ml/scripts/totals_generative/fit_copula.py` + 14 tests. ρ fit on the **residual** dependence after the E2.1 conditional means absorb shared park/weather/ump (distributional transform → normal scores → Pearson; discrete-marginal-correct), NOT raw pairs (double-count). **Operator run (11,659 eval games 2021–25): residual ρ = −0.0035** (Kendall −0.0046, naive raw +0.0002) → home/away runs are **essentially INDEPENDENT; the Gaussian copula is unnecessary** (global, no material bucket ρ). The corr AC passes; **the var(total) AC fails — but identically with and without coupling** (copula 15.15 ≈ independent 15.18 vs empirical 19.99, ~24% shortfall) ⇒ the totals variance deficiency (Story 29.1) is in the **MARGINALS, not the dependence.** The added **dispersion diagnostic** pins the cause: E2.1 fits the NegBin `r` on optimistic TRAIN-fit means → `r` biased high (under-dispersed); an **OOS-calibrated `r` (~4 vs train ~6–15) reproduces var(total) → closes the gap.** **➡️ E2.3: (1) drop the copula (convolve independently); (2) calibrate the per-side dispersion on held-out residuals.** `copula_v1.json` records ρ_global≈0; re-run once to bake the dispersion diagnostic into the ablation JSON/MD.

> **From E2.1 (gate-pass 2026-06-18) — two findings that shape this story:**
> 1. **Per-side calibration ≠ convolution calibration.** The E2.1 marginal already trends `calib_80` ≈ 0.77→0.81 (2025 fold 0.808), which is encouraging for E2.3's `calib_80 ≥ 0.80` gate — **but a ~calibrated per-side marginal does NOT guarantee the convolved total is calibrated.** Getting the home/away dependence right here is what makes (or breaks) that gate — treat E2.2 as load-bearing, not a formality.
> 2. **Dispersion `r` is non-stationary.** E2.1's fold `r` drifts ~33→8 over time (partly thinner early-train sets). So **don't assume a single global dispersion** any more than a single global ρ.

**Tasks:**
- [ ] Gaussian copula over the two NegBin marginals (the E2.1 `totals_perside_v1` artifact); fit ρ on historical (home_runs, away_runs) pairs from `mart_game_results`.
- [ ] Test conditioning **both ρ AND the dispersion `r`** on park/weather/run-environment buckets vs single global values; pick the simplest that fits (E2.1 flagged `r` drift; the same conditioning question applies to ρ).
**AC:** joint samples reproduce the empirical home/away run correlation **and** the realized total-runs variance; independent convolution (ρ=0) is shown insufficient on the tails (the variance/tail miss is the entire reason E2 exists); the ρ/`r` conditioning decision is recorded with its evidence.

### E2.3 — Convolution → predictive distributions  ✅  **[market-blind · PRODUCT-COMPLETE 2026-06-24: total + team-totals CALIBRATED; run-diff = documented near-miss (accepted)]**
> **✅ PRODUCT-COMPLETE 2026-06-24 (operator gate + per-side re-run, 11,662 eval games 2021–25; OOS purged CV).** `betting_ml/utils/totals_distribution.py` + `betting_ml/scripts/totals_generative/fit_totals_distribution.py` + `betting_ml/tests/test_totals_distribution.py` (17). **Dispersion-calibration thesis fully validated:** the leakage-safe expanding-window held-out `r` is **stable** (per-side `r_home`=4.03/CV 0.008, `r_away`=3.57/CV 0.023), fixing E2.1's under-dispersed train-fit `r`=8.5. **Total ✅ (calib_80 0.838, PIT-flat 0.0068)** and **both team-totals ✅ (home 0.863, away 0.847)** → the core totals deliverable (totals UX un-pause) is MET and serving-ready (`totals_distribution_v1.json`: per-side r + P05…P95 grid + `p_over`). **`run_diff` is a DOCUMENTED, ACCEPTED near-miss** on PIT-flatness (0.0303 vs 0.025; coverage 0.839 + center 0.503 are fine). **Cause is settled — two independent lines:** (1) synthetic — a correctly-specified model gives a flat run_diff (0.0067), so the miss is real, not a discreteness artifact, and dispersion asymmetry alone caps it at ~0.015; (2) the per-side re-run **moved home/away dispersion (r_home 4.03 > r_away 3.57) but left run_diff UNCHANGED (0.0301→0.0303)** → proving the miss is NOT dispersion but the **tiny home/away dependence the independent convolution omits by design** (E2.2: ρ≈0, negligible for the *total* which passes, but the *difference* is uniquely sensitive). **NOT chased — by design:** the only fix is re-introducing a copula, which contradicts E2.2 (dependence negligible; don't force a coupling the data doesn't support), and **run_diff is not a served surface** (the shipped H2H product uses the calibrated E13.6 model, not this distribution). So this is an honest finding (like E2.1b/E2.2's "NOT-MET = the finding"), not a blocker → **proceed to E2.5.** **🔒 Leak-guard RESOLVED:** `bp_eb_xwoba` ← de-leaked `eb_bullpen_team_posteriors` (E1.7; `appearance_date < game_date`, equal-weight trailing-30d pool), 96.5–98.9% populated 2018–2026 → marginals re-fit leak-clean automatically. **Calibration ≠ edge** (main total efficient per E13.8; derivative-edge = E2.6/E13.13). Params NOT promoted to S3 (gated at E2.6).
> **⚠️ Fold in the E2.2 finding (2026-06-22):** home/away runs are essentially **independent** (ρ=−0.0035) → **convolve the two marginals independently; do NOT couple.** E2.2 showed the ~24% total-variance shortfall is **marginal under-dispersion** (E2.1 fits `r` on optimistic train-fit means → ~8.5; the held-out `r` is **~3.7**), so E2.3's **first task is dispersion calibration: fit per-side `r` on held-out residuals** (leakage-safe rolling/prior-window) — the lever for the calib_80 gate. **Use a SINGLE stable `r ≈ 3.7`, not a per-period one — E2.1's "r drifts 33→8" is a train-set-size estimation artifact (held-out `r` is stable ~3.4–3.9 across folds), not real non-stationarity.** Reuse `betting_ml/utils/copula.py::sample_gaussian_copula_negbin` with ρ=0.
**Tasks:**
- [x] **Calibrate a stable per-side NegBin dispersion on held-out residuals** (leakage-safe expanding window; not E2.1's train-fit `r`, not per-period) — stable `r_home`=4.03/`r_away`=3.57; closes the variance gap. (Calibrated **per-side**, not a single shared `r`: the run-diff PIT is sensitive to the home/away dispersion asymmetry the sum is blind to.)
- [x] Draw N **independent** (home, away) samples (vectorized; cap N ~10k/game per §6; ρ=0) → derive **total** (sum), **run-diff** (difference; a distributional H2H input), and **team totals** (marginals).
- [x] Emit a quantile grid (P05…P95) + `p_over_<line>` for the relevant lines; store **params + grid, not raw samples** (§6).
**AC:** ✅ PIT-flat + `calib_80 0.838 ≥ 0.80` for the full-game total (fixed by the dispersion calibration, not a copula); ✅ team-total marginals PIT-calibrated; ⚠️ run-diff marginal is coverage/center-calibrated but misses PIT-flatness by 0.005 (0.0303 vs 0.025) — a documented, accepted near-miss (the residual home/away dependence the independent convolution omits by design; run-diff is not a served surface — H2H uses E13.6). See the status note above.

### E2.4 — First-5-innings (F5) per-side model  ⬜  **[market-blind]**
**Tasks:**
- [ ] A separate Stage-1 NegBin pair on **innings 1–5** run production (from `mart_pitch_play_event` / play-event marts) — starters dominate F5, bullpen barely matters → a different, often sharper signal, and a structurally softer market.
- [ ] Convolve via the same E2.2/E2.3 machinery → F5 total + F5 team totals + `p_over` at F5 lines.
**AC:** F5 distribution PIT-calibrated; **do not assume F5 efficiency — measure it** against the E2.0 F5 closes at E2.6.
> **🔴 F5 is BLOCKED ON A DATA SOURCE (E2.0b probe, 2026-06-18): The Odds API offers NO F5 lines at all** (`h2h_h1`/`totals_h1` = zero books, live or historical beyond 65 games in 2023). So there's **no F5 close to gate against** — not "thin," *absent*. **F5's fate is gated on E2.0c** (find an alternative source). **Do NOT build the F5 model until E2.0c secures an F5 odds source** — without one, an F5 distribution model has nothing to be evaluated against. If E2.0c finds no viable source, **F5 is killed** and the totals-derivative path leans on team/alt totals only.

### E2.5 — Signal registration + leakage-safe backfill  ⬜
**Tasks:**
- [ ] New version `totals_generative_v1` → `mart_sub_model_signals` (and/or a dedicated `totals_generative_signals` table mirroring `offense_v2_signals`); register in `sub_model_registry.yaml`.
- [ ] Backfill respecting `[[project_layer3_signal_leakage]]` — the scoring artifact must **not** have seen the scored season; only honest-OOS years are valid for any downstream eval.
**AC:** backfill passes the leakage check (in-sample seasons excluded from eval); signals refresh via the Dagster signal phase; versioned in the registry.

### E2.6 — Derivative pricing + validation gates  ⬜  **[needs E2.0 complete]**
**Tasks/AC (must clear before any derivative bet surfaces as actionable):**
- [ ] **Distributional accuracy:** convolved-total `crps_ensemble` beats the `total_runs` champion `crps_normal` under E1.1 CV, via `evaluate_promotion` (plug in as a `SamplesSpec` adapter — no gate changes).
- [ ] **Main-line un-pause (unchanged rule):** to bet main-line totals it must beat **both** prior-predictive NLL **2.8893** AND prior-naive Brier **0.248** on rolling-60 live.
- [ ] **Derivative edge (the real value path):** F5 / team-totals / alt-lines gated by **positive CLV vs *that derivative's own close* (from E2.0)** + **PBO<0.2 + DSR>0** (E1.4). ✅ E2.0's historical closes now exist (238k closes / 5,896 games). ⚠️ **Split the gate by market:** **team-totals + alt-totals** have history + live capture (E2.0b) → backtestable + forward — gate these now. **F5 has NO data source** (E2.0b probe: Odds API offers zero F5) → **F5 is on hold pending E2.0c**; don't include an F5 gate until a source exists (or F5 is killed).
- [ ] **FINAL STEP (§0.3):** generate the E2.7 app-session prompt and write it into §E2.7 (real PG table/columns/payload).

### E2.7 — Distribution UX  🧩  **[separate app session — prompt emitted by the E2 model session; see §0.3]**
**Scope:** render the predictive total/run-diff distribution + market-line rule + shaded favorable mass + an alt-line ladder, beside the existing per-pick SHAP `pick_explanation` (Story 30.15). Serve via Railway PG (params + quantiles only, never raw samples at request time). **AC:** distribution + drivers render on the pick detail page; honest-framing copy; changelog entry.
> **Totals-parity (E9.23):** this is the **honest home for the "totals win-probability CI"** the operator asked for (H2H parity). Include a **calibrated P(over) + an over-probability/total CI** from the E2.3 distribution on the totals pick detail — this is the real version (the current totals model's interval is un-calibrated; don't ship that). The CLV half of E9.23 is separate (E9.2, muted).

```
▶ App-session prompt — Story E2.7 (Distribution UX)  [app repo]
⏳ TO BE GENERATED by the E2 model session as its final task (§0.3), after E2.3/E2.6 produce the served
   contract. It must specify the ACTUAL Railway-PG table + columns (μ/σ, the P05…P95 quantile grid,
   p_over_<line>), the per-pick payload shape, and the serving path — then a fresh app session builds the
   pick-detail distribution + alt-line ladder + SHAP drivers per §0.2 + honest framing + changelog.
   Do not hand-author this prompt.
```

```
▶ New-session prompt — Epic E2 (copy into a fresh model-repo Claude Code session)

You are building Epic E2 (Per-Side Generative Totals) of the MLB Edge Program.
GOAL: home+away correlated NegBin run distributions → convolve → honest total/run-diff/team-total/F5
distributions → price the derivative markets the book sets lazily. Fixes Story-29.1 variance deficiency.

Read first:
  1. edge_program_implementation_guide.md — Epic E2 in full (§4) + §0 conventions + §5 gates + §6 cost
  2. edge_program_technical_spec.md — Workstream B
  3. betting_ml sub-model standard + offense_v2 generator (offense_v2/generate_offense_signals.py)
     — you BUILD ON its per-side NegBin (pred_runs_mu/dispersion), do not start from scratch
  4. sub_model_registry.yaml + scripts/evaluate_sub_model.py (registration + walk-forward eval)
  5. the master implementation_guide.md Story 29.1 + Epic 32 (the per-side-generative rationale)

SEQUENCING: E2.0 (historical derivative-odds backfill: F5/team-total/alt-total closes via Odds API historical
event-odds, shares the E5.0/E5.1 plumbing) is a SEPARATE Session-B data task that BLOCKS the E2.6 derivative
gate — kick it off early; it runs in parallel with the model build below. The backfilled odds are EVAL/CLV ONLY.

Build (market-blind model): E2.1 per-side NegBin → E2.2 Gaussian copula (fit rho on mart_game_results
home/away pairs) → E2.3 convolution + quantile grid → E2.4 F5 variant (mart_pitch_play_event) → E2.5 register
totals_generative_v1 (LEAKAGE-SAFE backfill per project_layer3_signal_leakage) → E2.6 gates (needs E2.0 done) →
FINAL STEP (§0.3): generate the E2.7 app-session prompt and write it into §E2.7 of the guide, filled with the
real Railway-PG table + columns (μ/σ, P05…P95 grid, p_over_<line>) and per-pick payload you produced.

GATES: crps_ensemble beats champion crps_normal (evaluate_promotion, SamplesSpec adapter); calib_80>=0.80;
main-line un-pause needs NLL<2.8893 AND Brier<0.248; derivatives need CLV-vs-own-close (vs the E2.0 closes)
+ PBO<0.2 + DSR>0 (use E1.4 utils — coordinate: E1 must exist for go-live, not for build).

⛔ MARKET-BLIND (architecture Principle 3 — non-negotiable): E2.1–E2.5 take ZERO market/odds/line/consensus
features — the market already prices our baseball info, so a model that sees the line just relearns it. Add a
CONTRACT-GUARD asserting no market columns in the feature matrix. Market data is allowed ONLY in E2.6's eval/CLV
and in E3/E4. COMPUTE (§6): copula sampling is the cost — vectorize (NumPy), cap N (~10k draws/game), run as a
DAILY Dagster batch op scoring only the upcoming slate, write PARAMS + QUANTILE GRID to the signal mart (raw samples to S3 only if the UX needs them).

Conventions: dbtf not dbt; Snowflake via MCP, fully-qualified, no USE; uv run python; hand >1min scripts
to the user; do not git commit/push; Dagster ops import packaged code only.
```

---

## 5. Epics E3 + E4 — Market Models (shared layer)

E3 and E4 are two heads of one market model and **share plumbing** (E3.0). Build the shared layer once.

### E3.0 — Shared market-data layer  ✅ **BUILT + LIVE-VALIDATED 2026-06-17** (one fast-follow open)  **[blocks E3.1, E4.1]**
**Tasks:**
- [ ] **Pinnacle ingest** (live fair-value anchor): timestamped Pinnacle via The Odds API `regions=eu` (Pinnacle is US-geo-blocked direct). Land on a flat-cost **Railway cron** (mirror A2.18's `services/odds_capture/` pattern) → Railway PG / `mart_odds_outcomes`; **not** a per-snapshot Dagster job.
- [ ] **De-vig utils:** reuse `betting_ml/utils/h2h_probability.py::devig_home_prob`, `totals_probability.py::devig_over_prob` — do not reinvent.
- [ ] **Line-movement features:** from `mart_odds_line_movement` (signed Δ pregame−open, h2h+totals), `mart_bookmaker_disagreement`, Parlay/Odds hourly snapshots, `feature_pregame_public_betting_features`. Plus point-in-time **deltas** of lineup (`feature_pregame_lineup_state`), starter scratches (`feature_pregame_starter_status`), weather (`feature_pregame_weather_status`).
- [ ] **Freshness flag** per sharp quote; never anchor to a quote older than a configurable window.
**AC:** a per-game market-feature frame (point-in-time, leakage-validated via `validate_scd2_reconstruction.py`), Pinnacle resolving for current games; no live Snowflake on any request path.

> **Status (operator session, 2026-06-17/18):** ✅ built + live-validated. Live frame = **`feature_pregame_edge_market`** (open/close, per-book divergence, dispersion, PIT starter + weather deltas, `pinnacle_quote_ts`/`pinnacle_lead_min` freshness); `assert_no_leakage_edge_market` passed in CI; Pinnacle resolving today (14 games, freshest quote ~01:31). The frame reads the **live path only** (`mart_odds_outcomes`, 2026+) per the deferred-union note — the dense **2021–2025 backfill feeds E4.3 / E3.0b, not this frame.**
> **Fast-follow (the one open box):** the **lineup-slot delta** is blocked on a missing `feature_pregame_lineup_state` dbt model (starter + weather have models; lineup doesn't). **Deferred / low-value now** — it primarily fed E3.1 (now no-edge); documented in the model header. Build only if a downstream story needs it.

### E3.0b — Bookmaker line-quality drift & historical recency-weighting  ✅ **BUILT 2026-06-18**  **[shared market layer · reusable analysis]**
> **Status:** built — `feature_edge_book_market_era_quality` quantified the decay (soft books' distance to Pinnacle ~halved 2021→2025). A genuinely useful standalone artifact (kept regardless of E4's death); commit when ready. Still feeds any future cross-book work (e.g. NCAAB mid-majors).
**Why:** bookmakers keep improving their own models and line-generation, so an *old* line from a book is a weaker benchmark than a recent one, and a book that was soft years ago may be sharp now. Treating all historical odds as equally informative biases every market backtest. **This analysis lives here, in the shared market layer**, because E3, E4, and the E2.0/E5 derivative/prop backtests all consume historical odds and must weight them consistently.
**Tasks:**
- [ ] **Per-book sharpness-over-time profiler:** for each book × market × season (or rolling window), measure line quality vs the realized outcome and vs the sharp consensus close — closing-line Brier / log-loss, vig level, and the CLV-beat rate of a naive follower. Track the trend.
- [ ] **Detect improvement / regime breakpoints** in a book's line quality (a book getting sharper, vig compression, a model overhaul). Flag the breakpoints.
- [ ] **Recency/quality weight per (book, market, era)** ∈ (0,1] (sharper-recent → higher; stale-soft-era → lower) as a parity-guarded canonical column, consumable by E3/E4 training + backtest sample weighting (multiplies with the E1.2 uniqueness / E1.6 regime weights) and by the E4.3 "use data where justified" rule.
- [ ] Document which book-eras are trustworthy enough to include vs down-weight vs drop.
**AC:** a per-(book, market, era) line-quality trend report + a recency-quality weight column consumed by the market backtests; a book shown to have materially improved has its pre-improvement data **down-weighted, not equal-weighted**.

### Epic E3 — Closing-Line / CLV Model  ⬜  **[Track C-market · own session]**
**Goal:** predict the market's own move (open→close) — a higher-SNR target than the game — so CLV is captured by construction. *(Market features ARE the point here — E3/E4 are the only place market data is allowed; §0.1.)*

#### E3.1 — Line-movement regression (Head 1)  🔴 **NO EDGE on first pass (2026-06-17)** — gated re-check folded into E4
> **Status:** first pass came back **no-edge** (operator, 2026-06-17, on then-sparse odds). A re-check on the now-dense 2021–2025 multi-book data is legitimate **only as a pre-committed, gated test** (purged CV + PBO<0.2 + DSR>0) — **not** a retry-until-green (the multiple-testing trap E1 exists to catch). **Fold the re-check into the E4 work** (it shares the dense data + the E3.2/E4.2 meta head) rather than a standalone retry; if it clears the gate there, revisit — otherwise the no-edge verdict stands. E4 (sharp-anchor) is the higher-prior edge and is the recommended next move.
**Tasks:**
- [ ] Target **Δ(open→close)** of the fair (de-vigged) line: h2h in prob units, totals in run units. Predict the point move **+ its uncertainty** (NGBoost Normal or quantile).
- [ ] Features from E3.0 (market-central, Layer 4): opening line + early movement, cross-book dispersion, public money%/ticket% split, point-in-time lineup/scratch/weather deltas; Layer-2 baseline as a fair-value anchor.
- [ ] Use **all available line-movement history where coverage justifies it**, applying the E3.0b recency-quality weights (weight, don't truncate).
**AC:** beats a "no movement" and a "momentum" baseline on OOS MAE under E1.1 purged CV; directional accuracy of the move CI strictly > 0.5.

#### E3.2 — Meta-label head (Head 2): P(beat the close)  ⬜
**Tasks:**
- [ ] Extend the converged Story-12.4 Bayesian meta-model; feed Head 1's predicted move + uncertainty as the strongest feature.
- [ ] Tune h2h and totals thresholds independently (base rates ~52.5% vs ~46.2%).
**AC:** top-quartile − bottom-quartile realized CLV gap ≥ 0.05 on the forward live set; calibrated P(CLV>0).

#### E3.3 — Timing / latency operationalization  ⬜
**Tasks:**
- [ ] The biggest predictable moves cluster on lineup releases, scratches, weather shifts. Tighten the Dagster `lineup_monitor_sensor` / pregame-snapshot cadence; **decommission the superseded `task_lineup_monitor`** (inventory flags it racing).
- [ ] Measure ingestion-to-line-move lead time — that lead *is* the edge Head 1 monetizes.
**AC:** lead time measured + reported; no double-write race; faster reaction to lineup/scratch/weather events.

#### E3.4 — Validation  ⬜
**AC:** forward CLV ≥ 100 live games, positive mean (the Story-12.5 gate; serving live since 2026-06-16) + PBO < 0.2 + DSR > 0 (E1.4); every feature point-in-time (`validate_scd2_reconstruction.py`).

```
▶ New-session prompt — Epic E3 (Closing-Line / CLV) (copy into a fresh model-repo session)

You are building Epic E3 (predict the close / CLV) of the MLB Edge Program. Build the E3.0 shared market-data
layer FIRST (it also serves E4); E3.0b (bookmaker line-quality drift weights) feeds the backtests.

Read first:
  1. edge_program_implementation_guide.md — §5 E3.0/E3.0b + Epic E3 in full + §0 conventions + §5 gates + §6 cost
  2. edge_program_technical_spec.md — Workstream C
  3. betting_ml/utils de-vig fns (devig_home_prob/devig_over_prob) — REUSE; mart_odds_line_movement,
     mart_bookmaker_disagreement, feature_pregame_meta_model_features
  4. master implementation_guide.md: Story 12.4 (Bayesian meta-model — Head 2 extends it), A2.18 (Railway
     odds-capture cron you mirror for Pinnacle), Story 12.5 (forward-CLV gate)

Build: E3.0 shared layer (Pinnacle ingest Railway cron → PG; de-vig; line-move + PIT delta features; freshness)
+ E3.0b bookmaker-drift weights → E3.1 Head 1 (predict Δ open→close, h2h+totals; NGBoost/quantile; use ALL
justified odds history with E3.0b weights) → E3.2 meta-label (extends 12.4; P(beat close)) → E3.3 timing/latency
(tune lineup sensor; decommission task_lineup_monitor) → E3.4 validation.

GATES: E3.1 beats no-move + momentum (E1.1 CV); forward CLV >=100 live games positive (12.5); PBO<0.2 + DSR>0.
Every feature point-in-time. Market features ARE allowed here (this IS the market model). COMPUTE (§6): Pinnacle
FETCH on Railway cron, dbt rebuild in Dagster; model is light → daily pipeline. No request-time Snowflake.
Conventions: dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run python; hand >1min scripts to user;
do not git commit/push; Dagster ops import packaged code only.
```

### Epic E4 — Cross-Book Sharp-Anchor  🔴 **CLOSED — no cashable edge (2026-06-18)**  **[Track C-market]**
> **Verdict (E4.3, dense 2021–26 data):** a **real, monotone CLV gradient — the program's first non-null signal — but too small to beat vig** (~0.5–0.9 prob-points CLV vs the ~4% soft vig) → **not cashable.** Pooled ROI negative, per-season noise, totals same. Killed on **ROI net of vig** (the cashability gate); the PBO/DSR harness was **not** run — it deflates *apparent positives*, it can't rescue a clear negative. **The CLV signal isn't wasted — it feeds the honest fair-value / transparency surfaces (E9.11/E9.12), just not as "+EV bets."** H2H straight-bet edge is now closed on both heads (E3.1 + E4); the betting-edge hope moves to **totals (E2) + props (E5)**. The latency-arbitrage thread (E3.3) is the only un-killed adjacency — parked (advisory/manual-incompatible; needs sub-second infra). E4.1–E4.6 below are **not built** (recorded for history).
**Goal:** bet the soft book toward Pinnacle when they diverge — the most likely real H2H edge, personalized per user book.

#### E4.1 — Per-book divergence signal  ⬜
**Tasks:**
- [ ] `edge_book = pinnacle_fair_prob − book_implied_prob` (both de-vigged) for `book ∈ {bovada, caesars, fanduel}`, per game/side, at decision time, using the freshest Pinnacle quote (not just close).
- [ ] Add cross-book dispersion (`mart_bookmaker_disagreement`); apply the E3.0 stale-quote freshness guard.
**AC:** per-book edge for all three soft books; a book missing a line is omitted gracefully (no error).

#### E4.2 — Meta-label: P(divergence bet beats the close)  ⬜
**Tasks:** shared head with E3.2; train on historical soft-vs-Pinnacle divergences and realized CLV/outcome; learn which gaps are real vs stale-quote artifacts. **AC:** meta separates profitable from unprofitable divergences on the honest subset (top vs bottom quartile CLV gap).

#### E4.3 — Backtest on all available odds history (coverage-justified)  ⬜
**Tasks:**
- [ ] Backtest "bet soft toward sharp" on **all odds data we have, for each (book, market) where coverage is sufficient to justify inclusion** — i.e. as the E2.0 / E5.1 / Pinnacle historical backfills land, **expand the backtest to cover them rather than capping at 2024+**. Apply the **E3.0b recency-quality weights** so improved-book eras down-weight stale ones (don't equal-weight or hard-truncate).
- [ ] Compute CLV-vs-soft-close and de-vig ROI net of vig, per book/era.
- [ ] Report **coverage realism**: how many games/day present a fresh, exploitable gap above threshold at bet time.
**AC:** backtest across the full justified history with per-(book, era) weighting; coverage report; PBO < 0.2. *(Supersedes the old "2024+ only" scope — expand as the backfills complete.)*

#### E4.4 — Selective bet rule + σ-Kelly (advisory)  ⬜  **[model/decision — app surface split to E4.6]**
**Tasks:**
- [ ] Take the soft-book side the sharp favors only when `edge_book > threshold` AND meta `P(profit) > tuned` AND the Pinnacle quote is fresh; size via σ-aware Kelly (Story 22.4), advisory only.
- [ ] Write recommendation rows with `book`, edge, Pinnacle fair value, freshness "as of" — the contract the E4.6 app surface renders.
- [ ] **FINAL STEP (§0.3):** generate the E4.6 app-session prompt and write it into §E4.6, filled with the real recommendation columns / PG table you produced.
**AC:** advisory rows carry book + edge + Pinnacle fair value + freshness; no auto-bet framing; E4.6 prompt emitted.

#### E4.5 — Validation  ⬜
**AC:** PBO < 0.2 + DSR > 0 + forward live CLV ≥ 100 games positive (same binding gate as E3).

#### E4.6 — Book-aware advisory app surface  🧩  **[separate app session — prompt emitted by the E4 model session; see §0.3 · extends A0.4.32]**
**Scope:** surface the per-book divergence advisory in Credence — filtered to the user's book, showing the book line, Pinnacle de-vigged fair value, the gap, conviction (meta P), and an "as of" timestamp; extends the A0.4.32 per-book comparison. Serve from Railway PG (precomputed). Honest framing (transparency, not a bet rec); changelog.
```
▶ App-session prompt — Story E4.6 (book-aware advisory surface)  [app repo]
⏳ TO BE GENERATED by the E4 model session as its final task (§0.3), after E4.4 produces the recommendation
   contract. Must specify the ACTUAL PG table + columns (book, side, edge, pinnacle_fair, meta P(profit),
   freshness ts) and serving path — then a fresh app session renders the per-book advisory (filtered to the
   user's book, Pinnacle anchor row) extending A0.4.32, per §0.2 + honest framing + changelog. Do not hand-author.
```

```
▶ New-session prompt — Epic E4 (Cross-Book Sharp-Anchor) (copy into a fresh model-repo session)

You are building Epic E4 (bet soft books toward Pinnacle) of the MLB Edge Program. REQUIRES the E3.0 shared
market layer + E3.0b drift weights (built in the E3 session, or build them first here if E3 hasn't run).

Read first:
  1. edge_program_implementation_guide.md — §5 E3.0/E3.0b + Epic E4 in full + §0 (esp. §0.3 app handoff) + §5 gates
  2. edge_program_technical_spec.md — Workstream D
  3. betting_ml/utils de-vig + compute_kelly (REUSE); mart_bookmaker_disagreement; A0.4.32 (per-book comparison —
     the live foundation E4.6 extends); Story 22.4 (σ-Kelly); Story 12.4 (meta-model — E4.2 shares E3.2's head)

RESOLVED: Bovada/Caesars/FanDuel = soft books users bet; Pinnacle = sharp anchor (LIVE, Odds API regions=eu).
Advisory only (manual betting); book-aware (edge computed PER book).

Build: E4.1 per-book edge (pinnacle_fair − book_implied, 3 books) → E4.2 meta-label (shared w/ E3.2) → E4.3
backtest on ALL justified odds history (E3.0b-weighted; expand as backfills land) + coverage realism → E4.4
selective rule + σ-Kelly (advisory) → E4.5 validation → FINAL STEP (§0.3): emit the E4.6 app-session prompt
into §E4.6 (real recommendation PG table/columns). E4.6 (the app surface) is then a SEPARATE app session.

GATES: PBO<0.2 + DSR>0 + forward CLV >=100 games positive. HONEST FRAMING: advisory; show Pinnacle anchor +
"as of" ts; no "+EV ⇒ bet". COMPUTE (§6): light model → daily pipeline; no request-time Snowflake.
Conventions: dbtf not dbt; Snowflake via MCP fully-qualified no USE; uv run python; hand >1min scripts to user;
do not git commit/push.
```

---

## 5A. App surfaces (Credence repo) — ported Edge-relevant A0.4 stories

These three master-guide stories are the app side of the Edge Program. **A0.4 is otherwise referenced in the master guide** (per scope decision); these three are carried in full because they directly surface Edge outputs. They are the consumption layer for E2/E3/E4 and the distribution UX (E2.7).

- **A0.4.32 — Per-book odds comparison (model vs. user-selected sportsbook).** ✅ SHIPPED 2026-06-17. Book selector {BetMGM, Caesars(`caesars`, not `williamhill_us`), FanDuel, DraftKings, Bovada, Pinnacle}; per book: offered price, de-vigged market %, model %, EV, edge; **Pinnacle always shown as the sharp reference**. Totals `model_prob` recomputed at *each book's own line* (Normal CDF on stored μ+σ, since the champion totals model is NGBoost-Normal — `totals_r` is never written). Served via Railway PG (`write_serving_store.py --book-odds` + `write_book_odds_op`). **This is the live foundation E4's book-aware advisory plugs into** — extend it with the `pinnacle_fair − book_implied` divergence + meta-label, keeping the transparency framing. **⚠️ REOPENED 2026-06-17 (see master guide A0.4.32 FA-1/FA-2):** post the Odds-API cutover, live Caesars now arrives as `williamhill_us` (NOT `caesars`) — the selector's `caesars` key is going stale and must be reconciled; **Fanatics** to be added (beta-user request) once the odds backfill fills the starter-key gap; and the book-odds PG cache is being moved to the Railway odds-capture cadence (no overnight refresh). E4.1's odds capture must assume the **main key** roster (starter tier drops fanatics/williamhill_us/rebet).
- **A0.4.33 — Decision-layer fields (conviction, gate signals, win-prob CI).** ✅ SHIPPED 2026-06-16. Real `game_conviction_score`, `gate_signals_met` (0–1 today; criteria 2–5 off), 80% Beta CI `win_prob_ci_*` on `daily_model_predictions`. Framed as confidence/transparency, partial-gate noted. **E2's distribution UX sits beside this band.**
- **A0.4.34 — CLV meta-model confidence bar (H2H + totals).** ⬜ NEW. P(CLV>0)+CI per pick: H2H `meta_*` (12.4), totals `totals_meta_*` (12.12). **#1 gotcha:** meta is written on the **morning row only** — coalesce it from the morning row onto the displayed (often post_lineup) pick (`MAX(...) OVER (PARTITION BY game_pk, game_date)`), or the bar never renders. Totals meta v0 has **no discrimination** (AUC 0.445, clusters ~0.604±0.009) → low-information styling, no conviction badge. **This is the app surface E3 strengthens** — as Head 1/Head 2 improve discrimination, this bar becomes informative.

> Full text + `▶ App-session prompt` blocks for A0.4.32/33/34 live in the master `implementation_guide.md`; copy those prompts directly for app-repo sessions. E2.7 (distribution UX) and E4.4 (book-aware advisory) are new app stories that extend A0.4.33 and A0.4.32 respectively, following the same patterns.

---

## 5B. Epic E5 — Player Props & Derivative Markets  ⬜  **[Track B-props · gated behind E1; builds on E2 + Epic 24]**

**Goal:** price per-player markets (pitcher strikeouts, batter total bases/hits, pitcher outs) against the book line, surface the projected distribution + edge on the A0.4.16 player pages, and validate any edge with the program's overfitting discipline. **Strongest thesis fit of any betting track** — props are the softest, most numerous markets, and we already model players in depth (EB posteriors, `starter_ip_v1`, archetype×cluster matchups, ZiPS/Steamer) with a prop feature mart (Epic 24 / Story 24.1) and player pages (A0.4.16) already built. The missing piece is market-line ingestion, which The Odds API event-odds endpoints provide.

**Why gated behind E1:** hundreds of prop markets ⇒ the highest multiple-testing/overfitting risk of any track. E1's PBO/DSR — applied **per market with a multiple-comparison correction** — is what keeps a "discovered" prop edge from being luck.

### E5.0 — Prop market ingestion (live)  ⬜  **[blocks E5.2+]**
**Endpoints (The Odds API v4):** GET events (`/v4/sports/baseball_mlb/events`) — FREE, get eventIds; GET event odds (`/v4/.../events/{eventId}/odds`) — props payload, `cost = (unique markets returned) × regions` per event (outcomes carry `description`=player, `name`=Over/Under, `point`=line; unsupported/empty markets are free); GET event markets — cheap discovery of offered markets. **Phase-1 keys** (confirm vs the betting-markets reference): `pitcher_strikeouts`, `pitcher_outs`, `batter_total_bases`, `batter_hits` (+ `batter_home_runs` opportunistic) — they map 1:1 to existing models.
- [ ] Raw tables (append-only, `ingestion_ts`, `raw_json`), staged with a lateral flatten mirroring `stg_parlayapi_odds`; grain `(ingestion_ts, event_id, book, market, player, outcome)`.
- [ ] Capture on a **flat-cost Railway cron** (mirror A2.18 `services/odds_capture/`); only the dbt rebuild stays in Dagster. Curated six books (A0.4.32); Pinnacle as the sharp prop anchor where offered.

**AC:** today's phase-1 prop lines land per book; credit spend logged (`x-requests-last`).

### E5.1 — Historical prop backfill (backtest dataset)  ⬜
**Tasks:**
- [ ] Backfill phase-1 prop markets via **GET historical event odds** (`cost = 10 × markets × regions` per event per snapshot; additional-market history only **after 2023-05-03**; 5-min snapshots; use GET historical events for eventIds), 2023-05-03 → present, **closing snapshot per game first** (+ optional open).
- [ ] Leakage-safe snapshot timestamps; reuse the E5.0 ingestion plumbing.
**AC:** game×player×market historical prop table; credit spend logged (≈0.5–1.1M credits — well inside 5M/mo; see credit math below).

### E5.2 — Per-prop distributional pricing  🔄  **[market-blind model · CODE-COMPLETE 2026-06-24, pending operator gate run]**
**Tasks:**
- [x] Price each prop from the player's predictive distribution: `pitcher_outs` → `starter_ip_v1` NegBin (`prob_over_negbin`, directly); ⭐ `pitcher_strikeouts` → **K = K-RATE × BATTERS-FACED** (`price_strikeouts`): p_k = log5(EB-shrunk pitcher K-rate [season→career→league], opposing-lineup `avg_k_pct_30d`, league) + a tempered catcher-framing logit nudge (γ=0.04; NO platoon/TTO term per the E13.2 temper); BF = outs-NegBin + reach-NegBin; K|BF ~ **Beta-Binomial(s)** with `s` a leakage-safe concentration calibration lever; `batter_total_bases`/`hits` → per-batter PA-outcome multinomial (`draw_batter_bases_hits`) from EB component rates + expected PAs.
- [x] Reuse E2.3's distributional machinery (`totals_distribution` PIT/calib_80/quantile-grid/p_over) + E1.1 `PurgedWalkForwardSplit` + the `market_blind` CONTRACT-GUARD; condition on expected workload via `starter_ip_v1` (Story 33.1 P(start) noted as a future enrichment, not yet built).
- [x] **Model-class bake-off + feature ablation** (`bakeoff_strikeouts.py`, operator-run; `--smoke` harness check): M1 compound-flat / M2 compound-recency / M3 LightGBM-Poisson-on-K / M4 Poisson-GLM, scored on purged-CV **CRPS + coverage@80 + PIT-KS + at-the-line ECE** (every candidate gets the same λ recalibration → fair), winner = min CRPS among well-calibrated, **PBO-guarded**; ablates rate-construction (career/season/30d/7d/blend) × framing × lineup-log5. Closes the "one model type" + "in-season recency" review gaps. Winner promotes into the served pricer.
- [x] **Recency-aware K-rate** (`build_predictors(rate_mode=…)`): the flat season+career rate is replaced/ablated by trailing-window K% (`k_pct_7d/30d`, `csw_3start`, velo trend — already in `feature_pregame_starter_features`), EB-shrunk toward career→league, so the rate tracks in-season stuff change. Forward-CV unchanged (leak-honest); recency lives in the features.
- [ ] **Operator runs** (>1-min Snowflake): STEP 1 bake-off → pick class+inputs; STEP 2 gate (`fit_prop_pricing.py`) with the winner → real calib_80 / PIT / per-line ECE + served params + `ablation_results/e5_2_{prop_pricing_calibration,strikeout_bakeoff}.{json,md}`. First gate run: lead `calib_80 0.859 ≥ 0.80` ✅, ECE ~0.035 ✅; PIT a documented near-miss (0.033 vs 0.025, post-λ) — the bake-off winner may close it.
**Build:** `betting_ml/utils/prop_pricing.py` (pure, 35 unit tests) + `fit_prop_pricing.py` + `bakeoff_strikeouts.py` (operator-run). E5.1 K-prop data in S3 (2023–25 + 2026). HONEST: calibration ≠ edge (`best_alpha = 0`); the edge is gated at E5.4.
**AC:** per-prop P(over/under) at the book's line; PIT-calibrated under E1.1 CV. *(machinery + harness met; numbers pending the operator run.)*

### E5.3 — Edge, de-vig & per-book comparison  ⬜
**Tasks:**
- [ ] Per prop × book: de-vig (reuse `betting_ml/utils`), compute `model_prob`, `edge`, EV; show Pinnacle as the sharp reference (extends A0.4.32 to props).
**AC:** per-prop per-book edge table; transparency framing (no bet-rec).

### E5.4 — Validation gates  ⬜  **[hard gate — props overfit easily]**
- [ ] Calibration `calib_80 ≥ 0.80` per prop type (E1.1 CV).
- [ ] Edge survives **PBO < 0.2 AND DSR > 0** (E1.4) **per market**, multiple-comparison-corrected across all markets tried (the crux — no cherry-picking the best prop type).
- [ ] Positive forward CLV vs the prop's own close; coverage-realism report (opportunities/day clearing the threshold).

### E5.5 — App surface (player pages)  🧩  **[separate app session — prompt emitted by the E5 model session; see §0.3 · extends A0.4.16]**
**Scope:** render the projected prop distribution + book line + favorable mass + drivers + per-book row (Pinnacle anchor) on the player pages. Serve from Railway PG (precomputed). Honest framing; changelog. **AC:** prop projection + comparison renders; no bet-rec framing.

```
▶ App-session prompt — Story E5.5 (prop projections on player pages)  [app repo]
⏳ TO BE GENERATED by the E5 model session as its final task (§0.3), after E5.2/E5.3 produce the per-prop
   payload. Must specify the ACTUAL PG table + columns (per-prop distribution/quantiles, book line, model_prob,
   edge, Pinnacle reference) and serving path — then a fresh app session renders them on the A0.4.16 player
   pages (distribution + book line + per-book row) per §0.2 + honest framing + changelog. Do not hand-author.
```

### E5.6 — DL zone-matchup signal (hitter hot-zone × pitcher cold-zone overlap)  ⬜  **[migrated from master Story 24.3 · MEDIUM · two-phase-gated · post-lineup only]**
**Hypothesis:** when a hitter's hot zones for a pitch type spatially overlap a pitcher's vulnerable zones for that *same* pitch type, the hitter wins the matchup more often → higher expected output. **Primary surface = props / fantasy + the player-page viz** (it lives at the hitter-vs-pitcher PA grain, exactly where props price); team-totals is a **cheap secondary probe only** (aggregating 9 hitters + bullpen dilutes it into the totals variance gap). **Post-lineup only** (needs the specific batter + starter) — must **not** be wired into the pre-lineup serve.
**Two-phase gate (a cheap probe gates the DL build — same pattern as master Story 31.5):**
- **Phase 1 — non-DL probe (do first; kill gate):** EB-smoothed per-hitter hot maps + per-pitcher vulnerability maps per pitch type from `stg_batter_pitches` (`plate_x/z`, `pitch_type`, `estimated_woba…`). Scalar overlap `= Σ_cells hitter_hot · pitcher_vulnerable · pitcher_location_freq` — the `pitcher_location_freq` term is a **required game-theory correction** (weight by where the pitcher *actually* throws; pitchers avoid hot zones, so a static overlap overstates it). Test correlation with realized per-PA output **and** incremental lift over the E5 prop baseline. **No correlation + no lift → do NOT build the CNN; ship the viz and document the null.**
- **Phase 2 — DL spatial encoder (gated on Phase 1):** multi-channel image (hitter heatmap + pitcher vulnerability [+ location] per pitch type) → small CNN / spatial-attention encoder → matchup embedding → prop outcome (or a scalar feature for the E5 model). The rare genuinely DL-appropriate problem here (a learned spatial convolution of two 2-D fields a linear feature can't represent). **Accuracy-first** eval (per-prop CRPS / calibration) vs the linear overlap and the E5 baseline; promote only on an accuracy win via `promotion_gate` + E1 PBO/DSR.
**Viz (independent of model verdict):** overlaid hitter-hot / pitcher-cold heatmaps per pitch type + the matchup score on the **A0.4.16 player pages** (extends the E5.5 surface) — useful explainability even at zero edge; a 🧩 app-session deliverable per §0.3.
**Tasks:**
- [ ] Phase 1: EB-smoothed zone maps + game-theory-corrected overlap; correlation + incremental-lift test vs the E5 prop baseline → explicit kill/proceed verdict.
- [ ] Phase 2 (if Phase 1 passes): CNN/spatial encoder; accuracy-first eval vs linear overlap + baseline via `promotion_gate` (+ E1 gates).
- [ ] Secondary probe: aggregate overlap → lineup-vs-starter; test totals lift (expected weak — document either way).
- [ ] Viz: heatmaps + matchup score on the player pages (extends E5.5); document the verdict (accuracy delta, calibration, edge if any).
**AC:** Phase-1 probe built with EB + the pitcher-location correction + an explicit kill/proceed verdict; if Phase 2 runs, promote accuracy-first only; viz shipped regardless; feature **not** in the pre-lineup path.
**Deps:** master Epics 4A/5A/16 + Story 18.1 + the E5 prop baseline; viz needs A0.4.16. *(Full original spec: master `implementation_guide.md` Story 24.3.)*

> **Credit math (Odds API @ 5M/mo):** live `markets × regions`/event → 4 markets × 15 games × ~6 refreshes ≈ **~11K/mo** (worst-case ~520K). Historical `10 × markets × regions`/event/snapshot → ~7,000 games × 4 × 10 ≈ **~560K one-time** (~1.1M for open+close). Both fit easily ⇒ **E5's binding constraint is overfitting discipline, not API cost.**

```
▶ New-session prompt — Epic E5 (Player Props) (copy into a fresh model-repo session)

You are building Epic E5 (Player Props) of the MLB Edge Program. GATE: may BUILD in parallel, but no prop
ships live until E1 (PBO/DSR) exists and the prop clears PBO<0.2 + DSR>0 per market (multiple-comparison
corrected) — props overfit easily.

Read first: edge_program_implementation_guide.md Epic E5 (§5B) + §0 + §5 gates; edge_program_technical_spec.md
Workstream E (props) + B (the distributional machinery you reuse); master implementation_guide.md Epic 24 +
Story 24.1 (EXISTING prop feature mart — build on it), A0.4.16 (player pages), A0.4.32 (per-book pattern),
A2.18 (Railway odds-capture cron), Story 33.1 (P(start)); betting_ml starter_ip_v1 (NegBin over outs — prices
pitcher_outs directly), starter_v1 (K%), batter EB posteriors, betting_ml/utils de-vig fns (REUSE).

THE ODDS API (5M credits/mo): GET events = FREE; GET event odds cost = markets×regions/event; GET historical
event odds = 10×markets×regions/event/snapshot, props only after 2023-05-03. Phase-1 keys: pitcher_strikeouts,
pitcher_outs, batter_total_bases, batter_hits. Books: betmgm, caesars, fanduel, draftkings, bovada, pinnacle.

Build E5.0 ingest (Railway cron) → E5.1 historical backfill (leakage-safe) → E5.2 per-prop distributions
→ E5.3 de-vig + per-book edge → E5.4 GATES → FINAL STEP (§0.3): generate the E5.5 app-session prompt and
write it into §E5.5 of the guide, filled with the real PG table + columns (per-prop quantiles, book line,
model_prob, edge, Pinnacle reference) you produced — the player-page UI is then a SEPARATE app session.
HONEST FRAMING: advisory; props carry heavy vig + low limits; transparency, not a bet rec. Conventions: dbtf
not dbt; Snowflake via MCP fully-qualified no USE; uv run python; hand >1min scripts to the user; do not git commit/push.
```

---

## 5C. Epic E6 — Feature-Engineering Audit  🟡 **CORE DELIVERED VIA E1.3; gap-analysis DEPRIORITIZED (2026-06-18)**  **[Track R]**
> **Update (E1 audit):** E1.3 already delivered this epic's core — the **redundancy finding** (the slim **14/31/19** contracts) + the **importance ranking** (**bullpen EB dominates** every target). The audit's conclusion — **more features ≠ edge** — **deprioritizes the gap-analysis (E6.3) new-feature hunting.** Action items that survive: **re-promote on the slim contracts** + invest in **bullpen modeling** (→ E2), not a generic feature search. Keep E6.2–E6.5 below as recorded method; don't spend session time hunting new features unless a specific, bullpen-adjacent hypothesis emerges.

**Goal:** a one-time systematic sweep of the entire feature surface (~690 columns in `feature_pregame_game_features` + sub-model signals) for overlooked engineering opportunities — missing interactions, transforms, contextual/temporal features, and dead-weight redundancy — producing a **prioritized feature-opportunity report**. The audit *finds* opportunities; each accepted opportunity becomes its own small feature-add story, tested through the E1 CV + promotion gate (no bloat — a new feature must earn its place).

**Why standalone:** we've never swept the feature surface end-to-end; near-uniform Layer-3 stacking weights strongly suggest both redundancy *and* unexploited structure. Kept out of the edge epics so feature spelunking doesn't stall E1–E5. Cheap, high-leverage, and it directly improves every model (betting + E8 projections).

### E6.1 — Feature inventory & taxonomy  ⬜
**Tasks:**
- [ ] Enumerate every model-input column (`INFORMATION_SCHEMA.COLUMNS` / dbt `catalog.json`); tag by family, source mart, transform type, rolling window, platoon split.
- [ ] Compute **live (pre-game) coverage** per column (% non-null at morning serve) to surface the Story-30.3 imputation risk (dense post-game, sparse pre-game).
**AC:** a complete feature-catalog table; pre-game-sparse families flagged.

### E6.2 — Redundancy & importance pass  ⬜
**Tasks:**
- [ ] Run E1.3 clustered MDA on the full surface under purged CV → cluster-level signal vs dead weight vs pure substitutes.
**AC:** ranked cluster importance; a "drop/consolidate" list (CI-crossing-0 clusters) + a "live signal" shortlist.

### E6.3 — Gap analysis (the creative pass)  ⬜
**Tasks:**
- [ ] Enumerate plausible-but-missing features and score by expected value × feasibility. Themes: **interactions** (park × fly-ball pitcher, wind × batted-ball, platoon × bullpen handedness, ump × pitcher CSW); **regime-normalized variants** (extend Story-27.7 beyond contact); **times-through-order / within-start fatigue**; **rest/travel × bullpen**; **catcher-pitcher pairing × framing × ump**; **pace & sequencing** from pitch data; **lineup construction/entropy** (revisit — was deprioritized).
- [ ] For each candidate, state a hypothesis + the source mart.
**AC:** a scored gap backlog in `ablation_results/feature_opportunity_audit.md`.

### E6.4 — Leakage & point-in-time screen  ⬜
**Tasks:**
- [ ] For every candidate, confirm an as-of-safe construction (no future/finalized-season leakage; SCD-2 / `validate_scd2_reconstruction.py` discipline).
**AC:** each backlog item tagged leakage-safe / needs-PIT-work / infeasible.

### E6.5 — Prioritized report + feed into the gate  ⬜
**Tasks:**
- [ ] Promote top candidates to individual feature-add stories, each validated under E1.1 purged CV + `evaluate_promotion` (must beat the **champion**, not the floor).
**AC:** the audit report is the source of a ranked feature backlog; nothing auto-merges.

> **Run mode:** this is an analytical sweep, not a pipeline — run it as an EC2/local batch over the training matrix cached to S3-Parquet (reuse `training_cache`); it reuses E1.3, so it's cheapest to run right after E1 lands.

### E6.6 — Home-grown Pitching+ (Stuff+ / Location+)  ⬜  **[first concrete BUILD off the E6 track · gated on the E1.6 history-extension appetite]**

**Why (surfaced 2026-06-17 during E1.6):** the slim totals/H2H/run-diff contracts use FanGraphs `home_starter_stuff_plus`, which has **two problems**: (1) a **hard 2020 floor** (FanGraphs' pitch model doesn't exist earlier) — the single feature that most blocks the E1.6 history extension to 2016; (2) it arrives through the **fragile FlareSolverr FanGraphs path** (`[[reference_fangraphs_flaresolverr]]`). Statcast pitch data (`stg_batter_pitches`) goes back to **2015**, so we can build our own. **Honest ROI framing — this is NOT justified by recovering a totals feature** (bullpen EB quality dominates totals; starter Stuff+ is only the #9 signal — see E1.3 cross-target finding). It is justified by: **(a) a genuinely NEW signal — Location+ (command/where-the-pitch-goes), which we do not ingest at all today; (b) full 2015+ history that unlocks the E1.6 extension for *every* model; (c) removing the FanGraphs/FlareSolverr dependency; (d) it is the right pitcher-quality input for E5 (pitcher-K props) and E8 (projections), where pitcher quality is central.** Build appetite is **decided by the E1.6 result** — if regime-weighted 2016+ history materially helps, that is the measured payoff that justifies this; if not, this stays a backlog item.

**Tasks:**
- [ ] **Per-pitch run-value target** from `stg_batter_pitches` (2015+): Statcast `delta_run_exp` if present, else count-state ΔRE from a run-expectancy matrix. This is the regression target both models predict.
- [ ] **Stuff+ model** — GBM predicting pitch run value from **physical characteristics only** (release velo, induced H/V movement, spin rate/axis, release point + extension, velo/movement differential vs the pitcher's primary fastball). **No location, no count.** Standardize to the conventional **100 = league average** scale; aggregate to pitcher-game (split starter vs bullpen).
- [ ] **Location+ model** (the NEW signal) — GBM predicting pitch run value from **location** (`plate_x`, `plate_z`) × **count** × batter handedness. Captures **command**, which Stuff+ deliberately ignores and which we have no feature for today. Same 100-scale + pitcher-game aggregation. (Optional **Pitching+** = a combined physical+location model.)
- [ ] **Validate vs FanGraphs** on the 2020+ overlap: our Stuff+ should correlate sensibly with `fg_stuff_plus_raw` (same construct sanity-check); Location+ should be **low-correlation with Stuff+** (proof it is additive, not redundant). Document agreement + any deliberate divergence.
- [ ] **Backfill 2015+ leakage-safe** → a sub-model signal mart (mirror `offense_v2_signals` / register in `sub_model_registry.yaml`); wire into `feature_pregame_starter_features` (+ bullpen) as-of (no future/finalized-season leakage; `[[project_layer3_signal_leakage]]`). **Compute (§6):** pitch-level fit is millions of rows → S3-Parquet/DuckDB or EC2 batch, NOT Snowflake CTAS; periodic, not daily.
- [ ] **Re-audit importance** (E1.3 clustered MDA, purged CV) across all three targets with the home-grown Stuff+ **and** Location+ in the surface: does Location+ earn a place (beat the **champion**, not the floor, per E6 discipline)? Does full-history Stuff+ rank higher than the FanGraphs version did? **Explicitly report whether it unlocks/improves the E1.6 2016+ extension** (re-run the E1.6 regime-weighted gate with these features available pre-2020).

**AC:** home-grown Stuff+ validated against FanGraphs (2020+ overlap, sensible correlation); Location+ demonstrated as a distinct (low-redundancy) NEW signal; both populated 2015+ and leakage-safe; clustered-MDA re-audit reports whether each earns its place vs the champion and whether it improves the E1.6 history extension. **Temper expectations honestly:** bullpen dominates totals, so the totals lift may be small — the win is the command signal, the full history, the dependency removal, and the E5/E8 leverage.

```
▶ New-session prompt — Story E6.6 (home-grown Stuff+ / Location+)

You are building Story E6.6 (home-grown Pitching+) of the MLB Edge Program — our own Stuff+ AND
Location+ from Statcast, replacing the FanGraphs Stuff+ (2020+ hard floor, fragile FlareSolverr path)
and ADDING a command/Location+ signal we don't have today.

GATING: build appetite is decided by the E1.6 history-extension result — confirm 2016+ regime-weighted
history materially helps before investing. This is a feature BUILD, validated through the E1 gate (must
beat the CHAMPION, not the no-skill floor).

Read first:
  1. edge_program_implementation_guide.md §5C Epic E6 (esp. E6.6) + §0 conventions + §6 cost
  2. E1.3 clustered_feature_importance.py + E1.6 run_env_regime.py / the slim contracts (the context that
     motivates this: bullpen dominates totals, starter Stuff+ is #9, FanGraphs is the 2020 floor)
  3. stg_batter_pitches (the 2015+ pitch source) + fg_stuff_plus_raw (FanGraphs, validate against, 2020+)
     + feature_pregame_starter_features (where the signal wires in) + sub_model_registry.yaml
  4. [[reference_fangraphs_flaresolverr]] (the dependency this removes) + [[project_layer3_signal_leakage]]

Build: per-pitch run-value target (Statcast delta_run_exp or count-state ΔRE) → Stuff+ GBM (physical chars
only) → Location+ GBM (location × count × handedness — the NEW command signal) → validate vs FanGraphs on
2020+ overlap (Stuff+ correlates; Location+ is low-corr ⇒ additive) → leakage-safe 2015+ backfill to a
sub-model signal mart + wire into starter/bullpen features → re-audit via E1.3 clustered MDA across all
three targets AND re-run the E1.6 regime-weighted extension with these features available pre-2020.

COMPUTE (§6): pitch-level fit is millions of rows → S3-Parquet/DuckDB or EC2 batch, NOT Snowflake CTAS;
periodic not daily. HONEST FRAMING: temper the totals expectation (bullpen dominates); the value is the
command signal + full history + dependency removal + E5/E8 leverage.

Conventions: dbtf not dbt; Snowflake via MCP, fully-qualified, no USE; uv run python; hand >1min scripts
to the user; do not git commit/push; Dagster ops import packaged code only.
```

### E6.7 — Pre-promotion prune validation (gate on the slim re-promote)  ⬜  **[Track R · BLOCKS the slim-contract re-promote · cheap, high-trust]**

> **⚠️ SEQUENCING (2026-06-18): run this AFTER E1.7 de-leak + E1.8 leakage sweep.** The slim **14/31/19** sets were chosen from an importance ranking topped by the leaky `bp_eb_xwoba` (#1/#2). That ranking is contaminated — once de-leaked, the bullpen xwOBA value drops out and `coverage_pct`/`uncertainty` rise — so **the prune must be re-derived on the de-leaked (and leak-swept) matrix before this validation means anything.** Don't validate/promote a prune built on leaked importances.
> **Update (E1.7 shipped 2026-06-18):** an **INTERIM** re-derive on the de-leaked matrix already exists (total_runs 14→**21**, home_win 31→**21**, run_diff 19→**15**; `elo_diff` + `pythagorean_win_exp_diff` now enter both H2H sets). These are **interim — re-derive once more after E1.8**, then run E6.7's validation on the final sets. **Candidate to drop:** `bp_eb_xwoba` survives only as a correlated *passenger* of `home_team_sequential_bullpen_xwoba` on the home side of home_win/run_diff — E6.7 may legitimately prune it (kept for now to preserve the reproducible E1.3 rule). Promotion-gate especially **home_win** (near-total 26-drop/16-add turnover).

**Why:** E1.3 produced the slim **14/31/19** contracts on **aggregate** clustered importance, and the plan is to re-promote champions on them. Before we ship a model with ~95% of its features removed, we must confirm the prune is *safe*, not just *smaller-on-average*. The user's two concerns are exactly right and become the gate: **(1) aggregate importance can hide *conditional* importance** — a feature near-useless on average but decisive in a specific game-state slice (extreme weather, bullpen-fatigue games, blowout-prone matchups) — so validate with **per-game (local) importance, not just the rough aggregate**; **(2) before trusting the prune, decide explicitly whether a dimensionality step (PCA) is warranted** rather than assuming.

**Recommended position on PCA (assess, but expect to reject — document the call):** PCA is most likely **the wrong tool here** and the story should prove it rather than apply it blindly. Reasons: (a) the champions are **gradient-boosted trees**, which are invariant to monotone single-feature transforms and already handle collinearity at split time — PCA's decorrelation buys little; (b) PCA produces **dense linear combinations** that **destroy the interpretability the product depends on** ("bullpen EB is your #1 driver" → "PC3 loads on 40 things"), breaking the SHAP `pick_explanation` surface; (c) rotating signal across many components can **dilute** a concentrated signal (bullpen EB) and *hurt* trees. The **redundancy** problem PCA is often reached for is **better handled by the clustered importance** already in E1.3 (which attributes importance across substitute features instead of splitting it). So: run PCA as a **diagnostic** (how many components capture the variance; is there a dominant collinear block) and report the explained-variance/condition number, but the **default recommendation is to keep raw, interpretable features pruned via clustered importance** — adopt PCA only if a measured accuracy win justifies losing interpretability.

**Tasks:**
- [ ] **Per-game (local) importance:** compute **SHAP** values per game on held-out folds for the *full* model; compare each candidate-dropped feature's **local** importance distribution to its aggregate rank. Flag any dropped feature with high local importance concentrated in an identifiable subpopulation (slice by weather, park, bullpen-fatigue state, rest, run-environment regime).
- [ ] **Stability across folds:** confirm the prune is not a single-split artifact — importance ranks / cluster membership stable across the E1.1 purged-CV folds (and across the three targets); the kept set should be the *intersection-stable* set, not one fold's ranking.
- [ ] **Slice-level parity, not just aggregate:** the slim model must match the full model **within game-state slices** (calibration + NLL by slice), not only on the pooled metric — this is what catches a conditionally-important dropped feature.
- [ ] **PCA assessment (diagnostic):** report explained-variance curve + condition number + the dominant collinear block; state explicitly whether PCA is adopted and why (default: **no** — keep interpretable features; redundancy handled by clustered importance). If a PCA/whitening variant is tested, it must **beat** the raw-slim model on held-out NLL to be considered, and the interpretability cost must be called out.
- [ ] **Decision record:** write `ablation_results/prune_validation.md` — kept/dropped per target, the slice findings, the PCA call, and a go/no-go on the slim re-promote (per-target — run_diff may go slim while another stays fuller).

**AC:** per-game SHAP + cross-fold stability + slice-level parity completed for all three targets; an explicit, documented PCA accept/reject; a per-target **go/no-go that gates the slim re-promote** (the roadmap "slim-contract re-promote" row does not ship until this passes). Honest framing: this protects against shipping a prune that looks fine on averages but is fragile in the game states that matter.

```
▶ New-session prompt — Story E6.7 (pre-promotion prune validation)

You are building Story E6.7 of the MLB Edge Program — validating the E1.3 slim 14/31/19 feature prune
BEFORE we re-promote champions on it. The bar: prove the prune is SAFE (not just smaller-on-average) and
make an explicit, documented call on whether any dimensionality reduction (PCA) is warranted.

Read first:
  1. edge_program_implementation_guide.md §5C E6.7 + the E1 audit finding (over-parameterized; slim 14/31/19;
     bullpen EB dominates) + §0 conventions
  2. E1.3 clustered_feature_importance.py + the slim contracts + E1.1 purged-CV utils
  3. the deployed champions (home_win / run_diff / total_runs) + their feature matrices

Do:
  - SHAP per-game (local) importance on held-out folds for the FULL model; compare each dropped feature's
    local importance to its aggregate rank; slice by weather/park/bullpen-fatigue/rest/run-env regime to find
    CONDITIONALLY important features the aggregate hid.
  - Cross-fold stability of ranks/cluster membership (and across all 3 targets) — kept set = intersection-stable.
  - Slice-level parity: slim vs full model must match on calibration + NLL WITHIN slices, not just pooled.
  - PCA DIAGNOSTIC only: explained-variance curve, condition number, dominant collinear block. DEFAULT = do NOT
    adopt PCA (trees handle collinearity; PCA kills the SHAP pick_explanation interpretability; clustered
    importance already handles redundancy). Adopt only if a PCA/whitened variant BEATS raw-slim on held-out NLL
    AND you document the interpretability cost.
  - Write ablation_results/prune_validation.md: per-target kept/dropped, slice findings, PCA call, go/no-go.

GATE: the slim re-promote does not ship until this passes per target. Conventions: dbtf not dbt; Snowflake via
MCP fully-qualified no USE; uv run python; hand >1min scripts to the operator; do not git commit/push.
```

---

## 5D. Epic E7 — Minor-League (MiLB) Data Ingestion & Rookie Gap Closure  ⬜  **[Track D-data · blocks E8 prospect projections]**

**Goal:** ingest minor-league data and build minor→major **translation factors (MLEs)** so players without an MLB track record get a real, performance-based prior instead of the generic archetype shrinkage (`k=200 PA`) the EB posteriors apply today. Improves rookie/call-up inputs for the betting sub-models, and is the **prerequisite data layer for E8's prospect projections.**

**Why:** the current EB posteriors shrink low-MLB-PA players toward an archetype prior; a rookie's actual AAA Statcast/performance is far more informative. AAA has had Hawk-Eye/Statcast since 2023, and minor-league box/game-log data is available via the MLB Stats API minor-league `sportId`s — so the data exists; the work is ingestion + translation.

### E7.1 — MiLB game-log / box ingestion  ⬜
**Tasks:**
- [ ] Ingest schedule + box + player game logs for AAA(`sportId`=11) / AA(12) / A+(13) / A(14) via the Stats API minor `sportId`s into append-only raw tables (mirror the `monthly_schedule`/statsapi pattern).
- [ ] Stage to per-player game logs with level, league, park, date.
**AC:** per-player MiLB game logs land with level/league/park/date + leakage-safe `ingestion_ts`.

### E7.2 — AAA Statcast ingestion (2023+)  ⬜
**Tasks:**
- [ ] Pull AAA Statcast (Hawk-Eye parks) where available into a `batter_pitches`-equivalent raw table, clearly level-tagged.
**AC:** AAA pitch/batted-ball data staged alongside MLB Statcast; coverage documented (not all parks/years).

### E7.3 — Minor→major translation factors (MLEs)  ⬜  **[the modeling crux]**
**Tasks:**
- [ ] Build level/league/park run-environment adjustments translating AAA/AA wOBA, K%, BB%, ISO (+ Statcast where present) into **MLB-equivalent** rates.
- [ ] Calibrate on graduated players (pre-call-up minor line vs realized MLB line) — supervised + backtestable.
- [ ] Emit a per-player MLB-equivalent line + uncertainty.
**AC:** documented, validated translation factors per level; MLE backtest error on the graduated-player holdout reported.

### E7.4 — Prospect identity & ETA xref  ⬜
**Tasks:**
- [ ] Cross-reference MLBAM / FanGraphs / prospect-list IDs; track level, age, ETA.
**AC:** a prospect dimension joining cleanly to the existing player xref and to E8.

### E7.5 — Wire MiLB priors into EB posteriors  ⬜
**Tasks:**
- [ ] Replace/augment the generic archetype prior with the MLE-translated MiLB line for low-MLB-PA players in `eb_batter_posteriors` / `eb_starter_posteriors`.
**AC:** rookie/call-up features carry a performance-based prior; ablation shows improved rookie calibration vs the generic-prior baseline (E1 CV).

### E7.6 — Coverage, SLA & leakage screen  ⬜
**Tasks:**
- [ ] As-of discipline (only MiLB stats available before the MLB game); freshness SLA; ingestion on the cheap surfaces.
**AC:** coverage report; no future leakage; Dagster coordinates, ingestion runs cheaply (Stats API free-tier; Savant CSV).

> **Cost:** MiLB data volume is large but ingestion is cheap (Stats API + Savant CSV, no per-call billing). Compute on S3-Parquet/DuckDB batch; don't full-rebuild marts intraday.

---

## 5E. Epic E8 — Fantasy / Dynasty Projections → **moved to its own guide**  ↗

**Fantasy/Dynasty is now a standalone guide:** `quant_sports_intel_models/baseball/fantasy/fantasy_dynasty_guide.md`. It's a distinct B2C vertical with its own data context (it references the master data inventory directly), users, validation bar ("match or beat ZiPS/Steamer," not a betting metric), and roadmap — and it's the seed for **multi-sport fantasy** (see the program multi-sport roadmap).

It still **belongs to this program**: it reuses E2's distributional machinery, depends on **E7** (MiLB MLEs) for prospects, the Story-33.1 playing-time model, and the §0 / §6 conventions; and per **§7A** it's plausibly the program's highest-value, most-defensible B2C bet (it doesn't require a market edge). The former E8.1–E8.8 stories now live there as **F1–F8**.

---

## 5F. Epic E9 — Beta User Request Backlog (living)  🔄  **[App lane · continuous intake; triage → route or build]**

**Purpose:** a single living home for beta-tester feature requests, so they're captured, triaged, and either routed into the owning epic or built as a small app story — instead of getting lost in chat. **This epic never "completes"** — it's the product feedback loop. Beta input is high-signal (it already drove much of A0.4), so requests here carry real weight.

**Intake & triage convention:**
- Every request gets a row in the backlog table: `ID (E9.n)`, date, requester, the request (verbatim where useful), a one-line interpretation, priority (P1/P2/P3), **home** (built here as an E9.x app story, or routed to an owning epic — e.g. E5 props, E8 fantasy, A0.4.x), and status (⬜ triage / 🔄 building / ✅ shipped / ↪ routed / ❌ declined w/ reason).
- **Honest-framing rule applies to every user-facing item** (no win-rate/edge/"+EV ⇒ bet" claims; transparency framing).
- Small UI/serving asks are built in place as E9.x app stories (Credence repo, Railway PG serving, changelog entry). Asks that need modeling are routed to the owning epic and tracked there, with a back-reference here.

### Backlog
| ID | Date | Requester | Request (interpreted) | Priority | Home | Status |
|----|------|-----------|----------------------|----------|------|--------|
| E9.1 | 2026-06-17 | beta user | Show the **+EV price range** per pick — the band of book odds over which the model still rates the bet +EV (moneyline first), so a user sees when a line move kills the edge. | P2 | E9.1 (app; extends A0.4.32/33) | ⬜ triage |
| E9.11 | 2026-06-18 | beta user | **Best price across top books** — for the model's value plays, surface which book offers the best price + a "+EV plays" view ranked by price. | P2 | E9.11 (app; extends A0.4.32 + E9.1) | ⬜ triage |
| E9.12 | 2026-06-18 | beta user | **Daily card** — the day's recommended plays + the price to get them at (honest: shows "nothing qualifies" when true). | P2 | E9.12 (app/serving; decision gate + E9.11/E9.13) | ⬜ triage |
| E9.13 | 2026-06-18 | beta user | **Keep the pick write-up up to date** — run the Mistral feature-importance explanation alongside/within `predict_today` (post-lineup) so it matches the served pick instead of a stale morning run. | **P1** | E9.13 (serving-pipeline; fixes 30.15 staleness) | ⬜ triage |
| E9.14 | 2026-06-18 | beta user | **Add Fanatics** to the Book Comparison on the pick-details page (curated book set). | P2 | E9.14 (app; extends A0.4.32) | ⬜ triage |
| E9.15 | 2026-06-18 | beta user | **Fix "Model Skill — All Picks" double-counting** — show ONE post-lineup production prediction per game (live + backfill), not morning+post_lineup duplicates. | **P1** | E9.15 (app/serving; metric correctness) | ✅ DONE 2026-06-18 |
| E9.16 | 2026-06-18 | beta user | **Paginate the Bet Log** (~25 picks/page). | P2 | E9.16 (app) | ⬜ triage |
| E9.17 | 2026-06-18 | beta user | **Bankroll-growth %** on Performance — net P&L ÷ editable initial deposit, alongside Net P&L + % ROI; user sets/edits their deposit. | P2 | E9.17 (app; settings + metric) | ⬜ triage |
| E9.18 | 2026-06-18 | internal | **Changelog accordion** — the changelog page is getting long (we're shipping a lot); collapse it into a per-week accordion so users can scan/expand rather than scroll a wall. | P3 | E9.18 (app; pure frontend) | ⬜ triage |
| E9.19 | 2026-06-18 | internal/security | **MFA on the application** — add multi-factor auth (Cognito TOTP) before Stripe / paying customers, so accounts (bet log, deposit, subscription) have account-takeover protection. | **P1 (security · gates E9.8 Stripe)** | E9.19 (app + backend/Cognito; GTM/paid-tier track) | ⬜ triage |
| E9.20 | 2026-06-18 | operator (live bug) | **🐞 P0 — pick ↔ narrative side mismatch.** Pick chip said "BAL ML / Model 79.2%" but the "Why this pick" narrative attributed the 79.2% to Seattle (and self-contradicted: "favoring the Mariners… favors the underdog Orioles"). A user can't tell which side the model backs → led to a wrong-side bet. | **P0 (live correctness/trust · money impact)** | E9.20 (app + serving/narrative) | ⬜ **top priority** |
| E9.21 | 2026-06-18 | operator | **PostHog metrics in Admin** — surface the PostHog product-analytics dashboard inside the website's Admin section so it's a one-stop view of site performance (DAU/active users, funnels, retention) alongside internal admin tooling. | P3 (internal/admin) | E9.21 (app; admin-only) | ⬜ triage |
| E9.22 | 2026-06-18 | operator | **Book Comparison odds-freshness** — the panel shows "Lines as of 7:00 AM CDT — updated hourly" but odds look stale / not refreshing at the stated cadence; the served lines + "as of" timestamp don't reflect the actual odds-capture frequency. | P2 (freshness/trust) | E9.22 (app + serving; **bundle with E9.1/E9.14 — same A0.4.32 surface**) | ⬜ triage |
| E9.23 | 2026-06-18 | operator | **Totals pick-detail parity** — H2H shows a win-probability CI + CLV confidence; totals shows neither. Wire up the totals equivalents. | P2 (parity) | E9.23 (app; **routes: CLV→E9.2 muted; CI→E2.7 gated on E2.3** — honest constraints below) | ⬜ triage |

### E9.20 — 🐞 Pick ↔ narrative side-attribution mismatch  ✅ **FIXED + SHIPPED 2026-06-18**  **[P0 · narrative-layer fix]**
> **Resolved 2026-06-18 — the narrative flipped, not the chip.** Source-of-truth: `calibrated_win_prob` is *always* P(home wins); for game_pk=823125 it was **0.208 = P(SEA)**, so the **chip was correct** ("BAL ML 79.2%" via `1−model_prob` for away picks) → **the model genuinely backed BAL, and the SEA bet was the wrong side.** The bug: `generate_pick_narratives.py` sent that 0.208 to Mistral **unlabeled** as "Model win probability," so the LLM attributed it to the picked team and produced the inverted/self-contradictory text. **Fix shipped:** (1) prompt **labels every prob by team** (`Model P(SEA wins): 20.8% / P(BAL wins): 79.2%`) + an explicit `"The model backs BAL to win."` keyed to `layer4_h2h_decision`; (2) edge display switched to `abs(cal_win − mkt_win)` to match the chip — **dropped the broken `h2h_edge=0.0`** (the known posterior bug, which had been feeding the narrative a wrong edge); (3) **`_validate_pick_consistency()` guard** — skips the Cortex call + logs `[E9.20 GUARD] SKIP` if `pick_side` direction contradicts `calibrated_win_prob` (catches future pipeline flips before users see them); (4) QUALIFY dedup → one Cortex call per `game_pk` (killed the ~5× duplicate calls); (5) 14 regression tests (`test_pick_narrative_guard.py`); changelog under week 2026-06-15. **No backend/dbt/frontend changes — the chip was never wrong. Systemic scope: AWAY-team picks were affected (home picks were coincidentally correct).** Operator regenerated today's narratives via `--reset-narratives`.

**Reported (operator, 2026-06-18) — with a real wrong-bet consequence.** On **BAL @ SEA, predicted Jun 18 1:11 PM CDT** (post-lineup), the surfaces disagree on *which team* the model backs:
- **Pick chip / structured pick:** `BAL ML` · **Edge +31.3%** · **BAL win — Model 79.2% · Market 48.0%**; 80% CI 73.6–84.6%. (Internally consistent: 79.2 − 48.0 ≈ +31.3 on BAL.)
- **"Why this pick" narrative (POST-LINEUP):** *"low win probability for the Orioles at 21%, favoring the Mariners with a 79% chance to win"* — attributes the **79% to Seattle** — then **self-contradicts**: *"the model takes a contrarian position, as it favors the underdog Orioles to win."*

So the chip says "bet BAL, model 79.2% BAL" while the narrative says "Mariners 79%." The operator read the narrative and bet SEA. **A user genuinely cannot tell which side the model favors → a wrong-side bet.** Top-priority correctness + trust bug (honest-framing rule: a self-contradictory pick explanation is especially damaging) with direct money impact.

> **Mechanic to suspect:** a **home/away (favorite/underdog) attribution flip.** SEA is home, so `home_win = P(SEA wins)`. The chip implies `home_win ≈ 0.208` (BAL 0.792); the narrative implies `home_win ≈ 0.79` (SEA). One layer inverted it. **First job is to establish source-of-truth** — what does the model actually output for this `game_pk`? — because that determines whether (a) the **narrative** flipped (chip right, BAL is the pick) or (b) the **serving/pick layer** mislabeled the side (narrative right, the *recommendation itself* is wrong and SEA was correct). **Do not assume the chip is right.**

**Investigation (find which layer flipped — don't guess):**
- [ ] **Source-of-truth:** pull the raw model output for this `game_pk` (`daily_model_predictions`, post_lineup row, champion `model_version`) — is the home-team win-prob 0.208 or 0.79? That single number adjudicates chip vs narrative.
- [ ] **Serving/pick layer** (`scripts/write_serving_store.py`, `app/backend/routers/picks.py`, `app/backend/models/picks.py`): trace how `pick_side` / `model_prob` / `market` / `edge` derive from `home_win` → assert the team label matches the probability (the home/away mapping).
- [ ] **Narrative layer** (`betting_ml/scripts/generate_pick_narratives.py` + `build_pick_explanations`, 30.15/E9.13): does the Mistral prompt receive the win prob **keyed to the correct team**, with unambiguous home/away labels? The self-contradiction implies flipped/ambiguous inputs. (The 30.15 follow-on already fixed a narrative win-prob *magnitude* bug + hallucinated-edge + the `h2h_edge=0.0` issue — this is the *team-attribution* facet.)
**Fix + guard:**
- [ ] Fix the layer that flipped so chip + narrative agree on side, prob, and edge.
- [ ] **Regression guard** (test + serve/build-time assertion): the narrative's favored side **must equal** `pick_side`, and `model_prob` must match the `home_win`→team mapping; **fail the serve/build if they diverge** — never ship a contradictory pick.
- [ ] **Audit scope:** check whether other games show the same flip (isolated or systemic?) and flag any picks served wrong-side.
**AC:** the BAL@SEA pick is consistent across chip + narrative + CI; source-of-truth identified and the flipped layer fixed; a guard blocks chip↔narrative side/prob/edge disagreement going forward; the isolated-vs-systemic audit is done; **changelog entry** (a correctness fix users should know about — especially anyone who saw the contradictory pick). **Deps:** 30.15/E9.13 (narrative pipeline) + the serving layer; relates to the broader attribution-bug pattern (E1.7/E1.8).

```
▶ Story prompt — E9.20 🐞 Pick ↔ narrative side-attribution mismatch   [App + serving/narrative · ⭐ P0 live bug]
APP TARGET: UI→frontend/ (pick chip + "Why this pick"); serving→scripts/write_serving_store.py + betting_ml/scripts/generate_pick_narratives.py; backend→app/backend/routers/picks.py + models/picks.py; ⛔ never the legacy Streamlit UI. `cat frontend/package.json` first.
BUG (real wrong-bet consequence): BAL @ SEA, predicted Jun 18 1:11 PM CDT. Chip = "BAL ML · Edge +31.3% · BAL win Model 79.2% / Market 48.0%". Narrative = "Orioles 21%, Mariners 79%" AND self-contradicts ("favors the underdog Orioles"). Operator bet SEA off the narrative. Users can't tell which side the model backs.
Read: §5F E9.20 + §0.2 + master Story 30.15 (build_pick_explanations) + E9.13 (generate_pick_narratives.py) + the serving layer (write_serving_store.py, picks.py, models/picks.py) + daily_model_predictions.
Do: (1) SOURCE OF TRUTH FIRST — pull the raw model output for this game_pk (post_lineup, champion model_version): is home_win ≈0.208 (BAL favored → chip right) or ≈0.79 (SEA favored → narrative right & the RECOMMENDATION is wrong)? SEA is home, so home_win = P(SEA). DO NOT assume the chip is correct. (2) trace home/away→pick_side/model_prob/edge in the serving/backend layer + the team-keying + home/away labels fed to the Mistral narrative prompt. (3) fix the layer that flipped so chip + narrative + CI agree. (4) ADD A REGRESSION GUARD: test + serve/build-time assertion that narrative-favored-side == pick_side and model_prob matches the home_win→team mapping — fail rather than ship a contradictory pick. (5) audit other games for the same flip; note any served wrong-side.
Gate/AC: BAL@SEA consistent across chip+narrative+CI; flipped layer fixed; guard blocks future side/prob disagreement; isolated-vs-systemic audit done; changelog entry. ⚠️ Honest-framing: a self-contradictory pick is a trust failure — fix at the source, not by patching the prose.
Closeout (per §0.1): END with an ⏭️ Operator handoff — run-order commands, `git add <paths>`, changelog line, verify-after-deploy (re-check this game_pk renders consistently).
```

### E9.21 — PostHog metrics in the Admin section (one-stop performance view)  ⬜  **[app · admin-only · P3 internal]**
**What it is:** surface the **PostHog** product-analytics view inside the website's **Admin** section so the operator has a single place to watch site performance (active/daily users, funnels, retention, top events) next to the existing admin tooling — instead of bouncing to the PostHog app. *(Beta is live: 5 testers, ≥3 DAU as of 2026-06-18 — this is the dashboard to watch that grow.)*

**Recommended approach (PM call — flag if you want it different):**
- **v1 = embed a PostHog *shared dashboard* (iframe) in an admin tab.** PostHog supports shared/embeddable dashboards via a share token. This is the fastest one-stop-shop: **no secrets in the frontend, no event-quota cost** (embedding doesn't consume the analytics allowance), and it reuses PostHog's own charts. Gate it behind the existing **admin-only** route.
- **v2 (only if v1 isn't enough) = pull metrics via the PostHog Query API server-side** (personal/project API key in `app/backend` env — **never** in the frontend bundle) and render native admin cards, so PostHog metrics sit *beside* internal numbers (users, picks served, bet-log) in one consistent UI. More work + key management; do it only if the embed's look/blend is insufficient. Free tier covers it (1M API requests/mo).

**Tasks:**
- [ ] Create the PostHog **shared dashboard** (DAU/WAU, signup→active funnel, retention, key events); generate its embed/share token.
- [ ] Frontend: an **Admin → Analytics** tab that embeds the dashboard (iframe), **behind the admin-only guard** (same gate as the blog editor); not reachable by regular users.
- [ ] If any API-key path is used, the key lives **server-side only** (`app/backend` env / secrets) — never shipped to the client.
- [ ] Document the dashboard URL + token location in `infrastructure/aws_resources.md` (or the app README).
**AC:** an admin can open Admin → Analytics and see the live PostHog metrics in-app; access is admin-only; no PostHog/API secret is exposed client-side; free-tier-safe (embed = no event cost). **No changelog** (admin-only, not an end-user-facing surface). **Deps:** existing admin section + admin-route guard; PostHog account (free tier). *(Security note: once E9.19 MFA lands, the admin login is a prime account to require MFA on.)*

```
▶ Story prompt — E9.21 PostHog metrics in the Admin section   [App · admin-only · P3]
APP TARGET: UI→frontend/ (Admin → Analytics tab); backend→app/backend/ ONLY if a server-side PostHog API-key path is used; ⛔ never the legacy Streamlit UI. `cat frontend/package.json` first.
Read: §5F E9.21 + §0.2 + the existing admin section/route-guard (the blog-editor admin pattern).
Do: v1 — create a PostHog SHARED dashboard (DAU/WAU, signup→active funnel, retention, key events) + embed it (iframe) in a new Admin → Analytics tab BEHIND the
admin-only guard. NO PostHog/API secret in the frontend bundle. If you instead pull via the PostHog Query API (v2), the key lives server-side in app/backend env only.
Embedding consumes NO event quota; free tier is ample. Document the dashboard URL/token in infrastructure/aws_resources.md.
Gate/AC: admin sees live PostHog metrics in-app; admin-only access; no client-side secret; free-tier-safe. NO changelog (admin-only, not end-user-facing).
Closeout (per §0.1): END with an ⏭️ Operator handoff — run-order commands, `git add <paths>`, verify-after-deploy (admin tab renders; non-admin blocked).
```

### E9.22 — Book Comparison odds-freshness (stale "as of" timestamp / cadence)  ⬜  **[app + serving · P2 freshness/trust · bundle with E9.1/E9.14]**
**Reported (operator, 2026-06-18):** the **Book Comparison** panel shows *"Lines as of 7:00 AM CDT — updated hourly,"* but the odds appear stale and don't seem to refresh at that cadence — they should update more often. So the served lines (and the displayed "as of" time + the "updated hourly" label) don't reflect the **actual** odds-capture frequency. Same class as E9.13's write-up staleness: the captured data is fresher than what's served.

**Investigate (find the cadence mismatch):**
- [ ] **Actual capture cadence:** how often does the odds-capture cron run (`services/odds_capture` / A2.18 pattern; E3.0 Pinnacle ingest) → `mart_odds_outcomes`? Is it hourly, or only at the daily/post-lineup pipeline run?
- [ ] **Serving refresh:** when is the **book-odds payload written to Railway PG** (`scripts/write_serving_store.py --book-odds` → the A0.4.32 payload read by `app/backend/routers/picks.py`)? If it only refreshes on the pipeline run, the panel shows that run's lines regardless of newer captures — the likely root cause.
- [ ] **Timestamp source:** is the "as of" time the **odds-capture timestamp** or the serving-write time? And is "updated hourly" actually true?
**Fix:**
- [ ] Refresh the book-odds serving payload on the **capture cadence** (or have the panel read the freshest captured lines), so the displayed lines move when the market moves.
- [ ] Make the **"as of" timestamp reflect the true latest odds-capture time**, and the cadence label match reality (honest-framing: don't claim "updated hourly" if it isn't).
**AC:** Book Comparison lines refresh at the real capture cadence; the "as of" timestamp + cadence label are accurate to when odds were actually pulled; verified against `mart_odds_outcomes` capture times. **Changelog** (user-visible freshness fix). **Deps:** A0.4.32 (book-comparison payload), the odds-capture cron (A2.18 / E3.0); **bundle with E9.1 or E9.14** (same surface) per operator request.

```
▶ Story prompt — E9.22 Book Comparison odds-freshness   [App + serving · P2]
APP TARGET: UI→frontend/ (Book Comparison "as of" + lines); serving→scripts/write_serving_store.py (--book-odds); backend→app/backend/routers/picks.py; ingest→services/odds_capture; ⛔ never the legacy Streamlit UI. `cat frontend/package.json` first.
Read: §5F E9.22 + §0.2 + master A0.4.32 (book-comparison payload) + A2.18 (odds-capture cron) + E3.0 (Pinnacle ingest) + mart_odds_outcomes.
Do: trace capture cadence (cron → mart_odds_outcomes) vs serving refresh (write_serving_store --book-odds → Railway PG → picks.py). Likely root cause: serving payload only refreshes on the pipeline run, not on the capture cadence → stale lines + wrong "as of"/"updated hourly". Fix: refresh book-odds at the capture cadence (or read freshest), make the "as of" timestamp the true latest capture time + the cadence label honest.
Gate/AC: lines refresh at the real cadence; "as of" + label accurate vs mart_odds_outcomes capture times; changelog. Honest-framing: the timestamp/label must be truthful.
Closeout (per §0.1): END with an ⏭️ Operator handoff — run-order commands, `git add <paths>`, changelog line, verify-after-deploy (open the panel, confirm the time matches the latest capture).
```

### E9.23 — Totals pick-detail parity (win-prob/distribution CI + CLV confidence)  🅿️ **DEFERRED (operator decision 2026-06-18) — leave totals bars OFF until the totals model is recovered (E2.3)**  **[app · P2 parity]**

> **✅ DECISION (operator, 2026-06-18): show NO totals bars for now** — neither the CLV bar nor a CI. Both honest versions depend on model work that isn't ready: the totals meta-model is non-discriminating (AUC≈0.445) and the totals point model is un-calibrated (the Story-29.1 variance deficiency E2 fixes). A muted-noise bar or an un-calibrated interval would mislead, and an empty/absent bar is the most honest state. **Revisit when the totals model is recovered — i.e. when E2.3 produces a calibrated totals distribution** (then E2.7 renders the real CI, and a discriminating totals meta-model can bring back a real CLV bar). No interim provisional CI.

**Reported (operator, 2026-06-18):** the H2H pick detail shows an **80% win-probability CI** + a **CLV confidence bar**; the totals section shows neither. The honest fix depends on the totals model recovery (above) — the two halves have different right homes and honesty constraints, so don't naively mirror H2H.

**The two halves (route each correctly):**
- **CLV confidence (totals) → already E9.2 (A0.4.34), but MUTED.** E9.2 surfaces both H2H and totals CLV meta bars. ⚠️ **The totals meta-model (v0) has near-zero discrimination (AUC ≈ 0.445) — it's essentially noise.** So the totals CLV bar must render **low-information / muted (no conviction badge)**, NOT as an equal-confidence mirror of H2H. It "appears" with E9.2; it becomes a *real* confidence signal only once a totals meta-model that actually discriminates exists. **Do not present noise as confidence.**
- **Win-probability / over CI (totals) → the honest version is E2.7, gated on E2.3.** The H2H CI works because that model emits a calibrated probability. The current totals champion has the **Story-29.1 variance deficiency** (under-dispersed — the entire reason E2 exists), so a CI drawn from it today would be a **miscalibrated interval shown as real.** The honest totals CI = the **E2.3 calibrated convolved distribution** (calib_80 ≥ 0.80 → real P(over) + quantiles) rendered via **E2.7 (distribution UX)**. So the proper "totals CI" is E2.7, fed by E2.3 — already in the roadmap.

**When revisited (post-totals-recovery), route each half:**
- **CLV confidence** → E9.2 pattern, but only once a **discriminating** totals meta-model exists (v0 is AUC≈0.445 noise). Until then, no totals CLV bar.
- **Win-prob/over CI** → **E2.7, fed by E2.3's calibrated convolved distribution** (real P(over) + quantiles). The current totals model's interval is un-calibrated — never ship it as a CI.
**AC (for now):** totals pick detail shows **no CLV bar and no CI** (the honest state); the card is **parked until E2.3 recovers the totals model**, then re-opened to wire the CI via E2.7 + a real CLV bar via E9.2. **Deps:** E2.3 (calibrated totals distribution) + E2.7 (distribution UX); E9.2 (CLV pattern).

### E9.1 — "+EV price range" (breakeven line) per pick  ⬜  **[app; extends A0.4.32 + A0.4.33]**
> **🔗 While in here (operator request 2026-06-18): also tackle E9.22** — the Book Comparison "as of 7:00 AM / updated hourly" timestamp is stale vs the real odds-capture cadence. Same A0.4.32 surface; bundle it with this card.

**Request (verbatim):** *"I think adding the line would help a lot. Like a range where the bet is still EV+. Mainly for moneyline teams. If LAD or something models out well from a range of lines. Say -110 to -125 is all +EV. That way you can see if lines shift on a book that no longer makes them a good bet."*

**What it is:** for a pick with model probability `p`, EV at decimal odds `d` is `EV = p·(d−1) − (1−p)`, which is **> 0 whenever `d > 1/p`** — i.e. whenever the offered price beats the model's **breakeven (fair) price** `d* = 1/p`. So the "+EV range" is simply *every price better than the breakeven price*. Surface it as the **breakeven American odds** plus the cushion to the current book price ("+EV down to −125; current −150"), so the user sees how far the line can move on their book before the edge is gone — and it flips to a clear "no longer +EV (per model)" state once the book price crosses breakeven.

**Why it's mostly glue (data already exists):**
- `daily_model_predictions` stores the model probability (h2h `calibrated_win_prob`; per-book de-vigged market % from A0.4.32). Breakeven `= 1/p` (decimal) → American; the EV + de-vig math lives in `betting_ml/utils` (`compute_kelly`, `devig_*`) — reuse, don't reinvent.
- This is a per-pick, per-book *display* extension of A0.4.32 (per-book odds comparison) + A0.4.33 (decision-layer fields). **Moneyline (h2h) first**; totals/run-line/props are the same formula on their own `p` and can follow.

**Tasks:**
- [ ] Backend: per h2h pick, compute `breakeven_american = toAmerican(1/p_model)` and `ev_cushion_vs_book` (current book price − breakeven), and add them to the A0.4.32 payload. Reuse the de-vig/EV utils; no new math.
- [ ] Express the band for the user's selected book (`+EV from <breakeven> and better`) with a boolean flag when the **current** book price has already crossed breakeven (no longer +EV).
- [ ] Frontend: on the pick / per-book comparison view, show the breakeven price + cushion (e.g. a "+EV to −125" chip beside "current −150"); refresh as the book price updates.
- [ ] Serving: precompute into Railway PG with the book-odds payload (A0.4.32 pattern); no request-time compute. Changelog entry.
- [ ] **Honest framing (required):** "+EV" here is **model-relative** — the point models have no demonstrated market edge (`best_alpha = 0`), so this is *"the model's breakeven price,"* a transparency / line-shopping aid, **not** a bet recommendation or a claim of real edge. No "+EV ⇒ bet" framing (pairs with the A0.4.32 guardrail).

**AC:** each h2h pick shows the breakeven American price + cushion vs the user's book; flips to "no longer +EV (per model)" when the book price crosses breakeven; framing is transparency, not a bet rec; changelog added.

> **Framing nuance worth shipping:** because we have no demonstrated edge over the close, the breakeven price is most honest shown **alongside Pinnacle's de-vigged fair price** (the sharp anchor, A0.4.32) — *"the model breaks even at X; the sharp fair price is Y"* is more truthful than implying our breakeven is the market's. Consider surfacing both.

### E9.11 — Best price across top books (line-shopping for the model's value plays)  ⬜  **[app; extends A0.4.32 + E9.1]**
**Request:** *"Get data from the top books to quickly see who is offering the best price on +EV plays."*
**What it is:** for each play the model rates as value, surface **which curated book offers the best (most favorable) price** + a **"+EV plays" view** ranked so the user line-shops to the best number. Mostly glue — A0.4.32 already pulls all six books per game/market into Railway PG.
**Tasks:**
- [ ] Backend: across the six books (`betmgm, caesars, fanduel, draftkings, bovada, pinnacle`), compute the **best available price** per play (side/market) + EV at that price; reuse the A0.4.32 payload + `devig_*`/`compute_kelly` (no new odds math).
- [ ] A **"+EV plays" endpoint/view**: filter to plays where `model_prob > best-book de-vigged price`; each row = play + best book + best price + the model breakeven (E9.1) + Pinnacle fair value.
- [ ] Frontend: highlight the best-price book per play; sortable "+EV plays" list (best edge first). Serve from Railway PG (precomputed, A0.4.32 pattern); changelog.
- [ ] **Honest framing (required):** "+EV" is **model-relative** (`best_alpha = 0`) — present as **line-shopping / where the model sees value at the best available price**, with the Pinnacle anchor; NOT "bets you'll win."
**AC:** per play, the best-priced book + EV; a +EV-plays view ranked by edge; Pinnacle anchor + breakeven shown; model-relative framing; changelog. **Deps:** A0.4.32, E9.1, `devig_*`.

### E9.12 — Daily card (the day's plays + the price to get them at)  ⬜  **[app/serving; uses the decision gate + E9.11/E9.13]**
**Request:** *"Could you have a daily card? What bets should be made and at what price?"*
**What it is:** one **daily card** of the model's recommended plays for the slate, each with **the price at which it's +EV** (the E9.1 breakeven) and the **best book offering it** (E9.11). The set = the **qualified plays** from the decision/permission gate (master Epic 19 `qualified_bet` / conviction) — selective by design.
**Tasks:**
- [ ] Backend: assemble the card from the **qualified plays** (Epic 19 `compute_bet_permission`/`qualified_bet`; A0.4.33 conviction/CI) ⋈ E9.11 best-price ⋈ E9.1 breakeven ⋈ Pinnacle fair value; precompute to Railway PG per `game_date`.
- [ ] Frontend: a **"Today's Card"** view — per play: side, the model fair/breakeven price, **best available price + book**, conviction (early/partial per A0.4.33), and the "why" (E9.13). σ-aware sizing (Story 22.4) shown **advisory-only**.
- [ ] **Honest empty card:** when **no plays qualify** (the common case — *"most games, most days, do nothing"*), say so plainly. The empty state is a feature, not a failure.
- [ ] **Honest framing (required):** the card is **the model's value plays at the model's prices** — advisory, model-relative, **not** "bets you will win." US betting is manual. Changelog.
**AC:** a daily card of qualified plays (side + breakeven price + best book/price + conviction + explanation); an honest empty state; advisory/model-relative framing; changelog. **Deps:** Epic 19 gate, A0.4.33, E9.11, E9.1, E9.13, Story 22.4.

### E9.13 — Keep the pick write-up up to date (run with `predict_today`, not morning-only)  🔄  **[serving-pipeline fix · P1 · fixes master Story 30.15 staleness]**
**Request:** *"A write-up about why the model says +EV … we feed feature importances through a Mistral model for a verbose explanation, but it keeps getting overwritten since it runs on the morning model — it likely needs to run alongside/within `predict_today` so the recommendation is up to date."*
**Root cause:** the LLM explanation (Mistral over the Snowflake feature-importance / SHAP attribution — master Story 30.15 `pick_explanation`) is generated on the **morning** pass; the **post-lineup `predict_today` re-score** then updates the recommendation but **not** the explanation → the served "why" is **stale / mismatched** (it explains the morning pick, not the served one).
**Fix / tasks:**
- [x] **Generate the explanation in (or right after) the post-lineup `predict_today` serve**, keyed to the served pick + its `prediction_type`/feature snapshot — `build_pick_explanations` wired into `_score_date`; `served_tier` set from lineup presence; `pick_explanation` written to every INSERT; **existing rows get a `pick_explanation` UPDATE + `pick_narrative = NULL`** on any re-score so the narrative always re-generates.
- [x] **Version, don't overwrite:** existing-row UPDATE path replaces pick_explanation + NULLs pick_narrative rather than inserting a second row; narrative re-generates automatically on the next `generate_pick_narratives.py` run.
- [x] **Cost guard (§6):** `generate_pick_narratives.py` filters `has_odds = TRUE AND pick_narrative IS NULL` — ~10–15 Cortex calls/day ($≈$0.05); prompt references EV (edge) explicitly.
- [x] **Honest framing:** `MODEL_REASONING_DISCLAIMER` updated to reference EV; narrative prompt instructs "EV = model-vs-market divergence, not guaranteed profit."
**AC:** the displayed explanation matches the **served post-lineup** pick (no stale morning text); explanations versioned (re-score → UPDATE + re-generate); LLM cost bounded to served picks; "what drove the pick" + EV framing. **Deps:** master Story 30.15 (the existing SHAP/Mistral pattern), `predict_today.py`, the pick surfaces; feeds E9.12.
**Implementation (2026-06-18):**
- `betting_ml/scripts/predict_today.py`: imports `build_pick_explanations`; DDL + ALTER adds `pick_explanation VARCHAR` + `pick_narrative VARCHAR`; `_score_date` determines `served_tier` from `lineup_present`, calls `build_pick_explanations`, passes `explanations` to `_write_predictions_to_snowflake`; dedup path UPDATEs `pick_explanation` / NULLs `pick_narrative` for existing rows.
- `betting_ml/scripts/generate_pick_narratives.py` (NEW): reads `pick_explanation IS NOT NULL AND pick_narrative IS NULL AND has_odds = TRUE`; builds prompt from SHAP drivers + EV metrics; calls `SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', …)`; UPDATEs `pick_narrative`. `--dry-run` flag. Hand off to operator to run with: `uv run python betting_ml/scripts/generate_pick_narratives.py --date <date>`
- `betting_ml/utils/pick_explanations.py`: `MODEL_REASONING_DISCLAIMER` updated to reference EV signal.
**Operator next step:** run `uv run python betting_ml/scripts/predict_today.py --date <today>` (dev env); confirm `[30.15]` log line appears; then run `uv run python betting_ml/scripts/generate_pick_narratives.py --date <today> --dry-run` to preview prompts before a live run.

### E9.14 — Add Fanatics to the book-comparison set  ⬜  **[app; extends A0.4.32 · small]**
> **🔗 While in here (operator request 2026-06-18): also tackle E9.22** — the Book Comparison "as of 7:00 AM / updated hourly" timestamp is stale vs the real odds-capture cadence. Same A0.4.32 surface; bundle it with this card.

**Request:** *beta user — add **Fanatics** to the Book Comparison on the pick-details page.*
**What it is:** add Fanatics to the curated book allowlist A0.4.32 uses (currently `betmgm, caesars, fanduel, draftkings, bovada, pinnacle`) so its price / de-vigged % / model % / EV / edge appear alongside the others — and flow into E9.11 (best price) + E9.12 (daily card).
**Tasks:**
- [ ] Confirm the Odds API **bookmaker key for Fanatics** (likely `fanatics`) and that it returns h2h + totals (+ props for E5) for current games.
- [ ] Add the key to the curated allowlist constant in `app/backend/routers/picks.py` + `write_serving_store.py --book-odds`; verify the odds ingest (`mart_odds_outcomes`) actually captures Fanatics — widen the ingest filter if it's being dropped.
- [ ] Frontend: Fanatics appears in the book selector + comparison rows; gracefully omit when it has no line for a game/market.
- [ ] Changelog (non-admin user-facing change).
**AC:** Fanatics shows in the pick-detail Book Comparison (price, de-vigged %, model %, EV, edge) for games where it offers a line; included in E9.11 best-price + E9.12 card; changelog added. **Deps:** A0.4.32; Odds API Fanatics coverage.

### E9.15 — Fix "Model Skill — All Picks" double-counting  ✅ DONE 2026-06-18  **[app/serving · metric correctness · P1]**
**Target:** `frontend/app/performance/page.tsx` `ModelSkillStrip` → FastAPI `/performance/model` → `mart_clv_labeled_games`.
**Root cause:** `mart_clv_labeled_games` `best_prediction` CTE partitioned only by `game_pk` and had no `model_version` filter — so `pre_lineup_v1` morning predictions could contaminate the v5 champion pick if v5 wasn't the latest `inserted_at` for a given game. Also no `is_backfill` ORDER BY preference (live vs backfill arbitrary under otherwise-tied rows).
**Fix:**
- [x] **`dbt/models/mart/mart_clv_labeled_games.sql`**: added `AND model_version = 'v5'` to `best_prediction` WHERE (pin to champion); added `CASE WHEN coalesce(is_backfill,false) THEN 2 ELSE 1 END` to ORDER BY (live > backfill). Grain `(game_pk, market_type)` uniqueness guard was already enforced via `dbt_utils.unique_combination_of_columns` in `dbt/models/mart/schema.yml`.
- [x] Schema description updated to reflect v5 pin + backfill handling.
**Operator:** `dbtf build --select mart_clv_labeled_games` then verify n_predictions in the app's Model Skill strip.
**AC:** ✅ one v5 prediction per game per market; ✅ pre_lineup_v1 excluded; ✅ live preferred over backfill; ✅ grain guard enforced at build time; no user-facing changelog entry (metric correctness fix, not a new feature).

### E9.16 — Paginate the Bet Log  ⬜  **[app · small]**
**Tasks:**
- [ ] Paginate the **Performance → Bet Log** list to ~**25 picks per page** (server-side or client-side over the existing DynamoDB bet-log payload); page controls + count; stable sort (date desc).
- [ ] Keep totals/summary (P&L/ROI) computed over the **full** log, not just the visible page.
**AC:** Bet Log shows ~25/page with working pagination; summary metrics stay full-history; changelog.

### E9.17 — Bankroll-growth % + editable deposit  ⬜  **[app · settings + metric]**
**What it is:** alongside the existing **Net P&L** and **% ROI**, add a **% increase on net investment** = `net_pnl / initial_deposit` (the user's bankroll growth — e.g. +$165 on a $200 deposit → **+82.5%**). Requires a **user-entered, editable initial deposit.**
**Tasks:**
- [ ] **User deposit field:** add an editable `initial_deposit` to the user profile (DynamoDB `credence-prod-dynamo-users`), set/edited from Settings (pairs with E9.10); default empty → hide the growth % until set.
- [ ] **Metric:** compute `bankroll_growth_pct = net_pnl / initial_deposit` and show it beside Net P&L + % ROI, **labeled distinctly** — ROI = return on amount staked (turnover); growth % = return on deposit. Don't relabel/replace ROI.
- [ ] (Extension, note only) multiple deposits/withdrawals over time → a running net-investment basis; v1 is a single editable deposit.
- [ ] **Honest framing:** these are the user's own tracked results (factual), not a model win-rate/edge claim; no extrapolation.
**AC:** with a deposit set, Performance shows Net P&L, % ROI, and a distinct **% growth on deposit**; the deposit is user-editable in Settings; growth hidden until a deposit is entered; changelog. **Deps:** DynamoDB users store; pairs with E9.10 (settings).

### E9.18 — Changelog accordion (collapsible per-week)  ⬜  **[app · pure frontend]**
**What it is:** we're shipping a lot, so the changelog page (`frontend/app/changelog`, reading `frontend/data/changelog.json`, A0.4.26) is becoming a long scroll. Turn it into a **per-week accordion** — one collapsible section per week (Monday→Monday grouping, see §0.2), so users can scan week headers and expand the ones they care about.
**Tasks:**
- [ ] Frontend only: render each `week` block as an accordion item (header = week label + a count/summary; body = the items). No data-shape change to `changelog.json` (still the same `[{week, items:[{tag,text}]}]`).
- [ ] **Default-expand the most recent week** (current Monday), collapse the rest; keyboard-accessible + ARIA (it's a disclosure pattern — see the accessibility-review skill).
- [ ] Preserve the tag styling (new/improvement/fix) within each expanded section.
- [ ] Optional: persist expand/collapse state for the session only (no browser-storage requirement).
**AC:** changelog renders as a per-week accordion, most-recent week open by default, others collapsed; keyboard/ARIA accessible; tag styling preserved; no change to the JSON contract; changelog entry (this is itself a user-facing change). **Deps:** A0.4.26 (existing changelog page); pairs with the §0.2 Monday-grouping convention.

### E9.19 — MFA on the application (Cognito TOTP)  ⬜  **[⭐ P1 security · app + backend/Cognito · GTM/paid-tier track · HARD GATE before E9.8 Stripe / paying customers]**
**Why:** before there's a billing relationship and real money in play, accounts need **account-takeover protection.** We don't store card data (Stripe Checkout holds it — E9.8), but a compromised account still exposes the user's bet log, tracked deposit, and subscription. MFA is table-stakes security to have **in place before paying customers exist.**

**Recommended design (PM call — flag if you want it different):**
- **Method: TOTP (authenticator-app / software token) via Cognito**, not SMS. TOTP is free (no SNS/SES cost), not vulnerable to SIM-swap, and Cognito supports it natively (`associateSoftwareToken` / `verifySoftwareToken` / `respondToAuthChallenge`). SMS can be a later fallback if users ask, but it's weaker and metered.
- **Enforcement: optional-but-encouraged in beta → mandatory for `subscriber`-group accounts at Stripe launch.** This avoids adding friction to beta onboarding while guaranteeing every *paying* account is protected. (Open decision: if you'd rather make it mandatory for everyone now, say so — it's a one-line policy change in the enrollment gate.)
- **Federated (Google/E9.7) users** inherit MFA from their Google account → the Cognito-TOTP enrollment applies to **username/password accounts**; note this so we don't double-prompt.

**Tasks:**
- [ ] **Cognito:** enable the **software-token (TOTP) MFA** option on `credence-prod` user pool (MFA = optional at pool level so per-user enrollment is possible; enforcement policy applied in-app per the decision above).
- [ ] **Frontend — enrollment:** an MFA section in `frontend/app/settings` (security) — "Enable two-factor": `associateSoftwareToken` → render the QR / secret → user enters a code → `verifySoftwareToken` → `setUserMFAPreference(TOTP)`. Show enabled/disabled state + a disable flow (re-auth required).
- [ ] **Frontend — login challenge:** handle the `SOFTWARE_TOKEN_MFA` challenge in the login flow (`frontend/app/login` + AuthContext) — prompt for the 6-digit code → `respondToAuthChallenge`. Clear errors for wrong/expired codes.
- [ ] **Backend:** minimal — Cognito drives the MFA flow; touch `app/backend/routers/auth.py` only if a status/enforcement endpoint is needed (e.g. block `subscriber` access until MFA enrolled, when enforcement turns on). No new email (TOTP needs none).
- [ ] **Recovery:** a documented account-recovery path for a lost authenticator (admin-assisted reset for beta; self-serve recovery codes can be a follow-up).
- [ ] **Changelog** (user-facing security feature).
**AC:** a user can enroll TOTP MFA from Settings (QR → verify → enabled), is challenged for the code on next login, and can disable it with re-auth; federated users aren't double-prompted; the enforcement policy (optional now / mandatory for subscribers at launch) is implemented as a single gate; **E9.8 (Stripe) does not go live until this is in place.** **Deps:** Cognito pool (A0.4.9), AuthContext (A0.4.2); **gates E9.8 (A0.7)**; pairs with E9.7 (OAuth) for the federated-user note.

```
▶ Story prompt — E9.19 MFA on the application (Cognito TOTP)   [App + backend/Cognito · ⭐ P1 security · gates E9.8 Stripe]
APP TARGET: UI→frontend/ (settings security + login challenge); backend→app/backend/ only if a status/enforcement endpoint is needed; Cognito console for the pool MFA setting; ⛔ never the legacy Streamlit UI. `cat frontend/package.json` first.
Read: §5F E9.19 + §0.2 + master A0.4.9 (Cognito pool) + A0.4.1/A0.4.2 (login + AuthContext) + A0.6B/E9.7 (federated users) + A0.7/E9.8 (the Stripe rollout this gates).
Do: enable software-token (TOTP) MFA on the credence-prod Cognito pool (optional at pool level). Frontend enrollment in settings: associateSoftwareToken → QR/secret → verifySoftwareToken → setUserMFAPreference; enabled/disabled state + disable-with-re-auth. Frontend login: handle the SOFTWARE_TOKEN_MFA challenge → respondToAuthChallenge with clear errors. Enforcement: optional-but-encouraged in beta → mandatory for the subscriber group at Stripe launch (single in-app gate; confirm the policy with the operator). Federated (Google) users inherit MFA from Google — apply Cognito TOTP to username/password accounts only, no double-prompt. Document a lost-authenticator recovery path (admin-assisted for beta).
Gate/AC: enroll (QR→verify→enabled) + login challenge + disable-with-re-auth all work; subscriber-enforcement gate implemented; no double-prompt for federated users; E9.8 stays blocked until this is live; **changelog entry (user-facing security feature).**
Closeout (per §0.1): END with an ⏭️ Operator handoff — run-order commands (incl. any Cognito console step), the `git add <paths>`, and verify-after-deploy.
```

### Migrated app/infra backlog (from master `implementation_guide.md` Epic A0)
These existing app/infra stories now live here — **E9 is their tracking home.** Full specs remain in the master guide under the cited A0 IDs; they run as app/infra sessions (mostly pure app-repo with no model upstream → authored directly per §0.3). Status as of migration (2026-06-17):

| ID | Source | Story | Pri | Status | Home / key deps |
|----|--------|-------|-----|--------|-----------------|
| E9.2 | A0.4.34 | CLV meta-model confidence bar (**H2H only**) per pick | P2 | ✅ SHIPPED 2026-06-18 | H2H CLV bar on the pick detail; **totals excluded** (low-info, per E9.23). Fixed the **NULL-meta-columns** serve-side gap (`arviz`+`h5netcdf`) + `MAX() OVER` so morning meta survives to post-lineup rows. **Weekly retrain (INC-1) ✅ resolved** (pymc/h5py added) → trace refreshes → bar stays fresh. CLV = line-value leading indicator, not a bet rec |
| E9.3 | A0.4.31 | Live scores via the Odds API scores endpoint → Railway PG | P2 | ⬜ NEW | app + poller; poll only while games in-progress (cost guard); MLB StatsAPI fallback |
| E9.4 | A0.4.18 | Cognito welcome email + beta-user onboarding | P1 | ✅ SHIPPED 2026-06-18 (beta onboarding live) | branded invite + verification templates (atomic both-together push); SES bounce/complaint handling (suppression + SNS→support@ + config set, simulator-verified); e2e verified; **beta users provisioned** |
| E9.5 | A0.4.22 | Password reset flow | P1 | ✅ SHIPPED 2026-06-18 | app + backend; validated end-to-end with a real non-sandbox email; branded SES template; `POST /auth/verify-email` auto-verifies admin-created accounts (`CognitoEmailVerify` IAM + lambda redeployed) |
| E9.6 | A0.4.17 | Morning early pick (pre-lineup "preliminary" surface) | P3 | 🔶 PARTIAL | app done; pipeline blocked on master Story 30.8 (morning-mode model). Pairs with the Edge pre-lineup theme |
| E9.7 | A0.6B | Google OAuth / social sign-in | P1 | ⬜ | app; Cognito federated identity; **unblocks E9.8** |
| E9.8 | A0.7 | Stripe subscription billing (Starter/Pro; Cognito groups) | P1 | ⬜ | app + backend; needs E9.7 + Cognito groups (E9.4) — the **paid-tier revenue gate**; ⛔ **also gated by E9.19 (MFA) before live mode / paying customers** |
| E9.9 | A0.6 | Push notifications (AWS SNS + Lambda + Web Push / SES) | P1 | ⬜ (SES email path now live) | backend; Dagster publishes post-`predict_today`; **SES email path unblocked 2026-06-18** — remaining work is the SNS/Lambda/DynamoDB/Web-Push build (no longer SES-blocked) |
| E9.10 | A0.4.11 | Settings: user profile + notification preferences | **P1 (window: unblocked parts only)** | ⚠️ PARTIAL | app; **window scope = profile + sign-out + non-email prefs + editable `initial_deposit`** (no new deps). The **email/push notif toggle is deferred to E9.9** (SES is no longer the blocker — E9.9's backend build is) — not in the current card |

> **🟢 SES PRODUCTION GRANTED (2026-06-18):** account out of the SES sandbox, **50,000 msg/day, 14 msg/s, us-east-1**. This **unblocks E9.4 (invites), E9.5 (reset emails), and E9.9's email path**, and **retires the Resend "Path B" contingency** (use SES Path A directly). Set up bounce/complaint handling per AWS best-practices before high-volume sending; the mailbox simulator is the safe test target.
> **Sequencing notes:** **E9.7 → E9.8** (OAuth → Stripe) is the **paid-tier revenue path** — sequence them together once beta stabilizes. **E9.4 + E9.5 are now quick beta-launch enablers** (SES live) — E9.4 is the literal gate to inviting beta users. E9.6 pairs with the pre-lineup serving theme (master Story 30.8 dependency). E9.2 is also the CLV-bar app surface that Epic E3 strengthens.

---

## 5G. Epic E10 — Parlay Recommendation System  ⬜  **[beta-driven + product differentiation · honest-MVP-first]**

**Migrated from master `implementation_guide.md` Epic 34.** A beta-requested feature with real differentiation potential — but parlays compound vig and our straight bets have no demonstrated edge, so this ships an **honest calculator first** and a recommender **only if/when a live edge source exists.**

**Why it's here (beta + differentiation):** beta users asked for parlay recommendations (2026-06-16). The differentiation is *not* a naive "combine today's picks" tout (that actively loses money at zero edge) — it's a **decision-support calculator** that tells users the truth about any parlay (true vs implied probability, +EV or not, correlation-aware). That's useful even at zero model edge and builds trust; the recommender is gated behind a real edge source.

#### E10.1 — Parlay decision-support calculator (the honest MVP)  ⬜
**Tasks:**
- [ ] Build-your-own-parlay: user selects legs → return true combined probability (from our per-leg model probabilities), book implied probability (from parlay odds), EV, and a plain-language verdict.
- [ ] **Correlation-aware:** same-game legs use a correlation adjustment (not naive independence); stamp the source (joint model / historical pairwise / prior constant). Reuse Epic 22.1 pairwise correlation.
**AC:** calculator returns true vs implied prob + EV + verdict for any user-built parlay; same-game legs correlation-adjusted (source stamped); honest framing (most parlays are −EV after vig — say so). No model edge required.

#### E10.2 — Book SGP / parlay-price ingestion (feasibility spike)  ⬜🔒
**Tasks:**
- [ ] Determine whether the Odds API / Parlay API surfaces same-game-parlay prices (without them, SGP mispricing can't be measured).
**AC:** a go/no-go feasibility verdict + (if available) an ingestion path.

#### E10.3 — Correlation-aware +EV parlay recommender  ⬜🔒  **[HARD GATE]**
**Tasks:**
- [ ] Search for +EV parlays and recommend them. **Does NOT start until Epic 30 serving-honesty is confirmed AND ≥1 leg market is live-edge-validated** (E4 sharp-anchor conviction forward-test passed, OR E5 props showing edge). Use E2's joint distribution for same-game correlation.
**AC:** the recommender only surfaces parlays whose legs are individually edge-validated; otherwise an honest empty state; PBO < 0.2 + DSR > 0 on the parlay return series (E1.4).

#### E10.4 — Parlay staking (parlay Kelly)  ⬜🔒
**Tasks:**
- [ ] Size recommended parlays via fractional Kelly on combined odds/probability; account for correlation with same-day straight bets (Epic 22.2).
**AC:** parlay stakes correlation-adjusted vs the day's straight-bet exposure; advisory only.

#### E10.5 — Frontend parlay surface  🧩  **[separate app session — prompt emitted by the E10.1/E10.3 session; see §0.3]**
**Scope:** calculator UI (always available) + recommender tab (gated; honest empty state until E10.3 qualifies). Serve from Railway PG; changelog.
```
▶ App-session prompt — Story E10.5 (parlay UI)  [app repo]
⏳ TO BE GENERATED by the E10.1 (calculator) / E10.3 (recommender) session as its final task (§0.3), with the
   real calculator endpoint + (if live) recommender payload columns. App session then builds the calculator
   (always on) + recommender tab (gated empty state) per §0.2 + honest framing + changelog. Do not hand-author.
```

**Sequencing & kill criterion:** Phase 1 = E10.1 calculator + E10.2 feasibility + E10.5 calculator UI (honest value now, zero edge required). Phase 2 = E10.3 recommender + E10.4 staking (after Epic 30 + ≥1 live edge source). **Kill:** if E10.2 finds no SGP pricing AND no leg market clears a live-edge gate, the epic terminates at the calculator (still a genuinely useful honest tool) and the recommender closes as "no edge to recommend."

---

## 5H. Epic E11 — Infrastructure & Cost Savings  🟢 **ACTIVE 2026-06-18**  **[cost initiative · execution home for §6]**
> **🟢 ACTIVATED (operator 2026-06-18): "keep Snowflake at the MINIMUM until profitable."** Snowflake ≈ 60% of pre-revenue burn, +25% MoM → cost-opt is now active work (not parked). Lead with **E11.2 Task 2 (daily state-aware builds — quick win)** + **E11.1 Wave 1 (heavy Tier-3 Statcast marts → dbt-duckdb/S3)**. The **6/22 Snowflake/Dagster audit** measures the delta vs the cost baseline (build_roadmap *Cost watch*) and prioritizes the next wave. **Live serving/predict path stays on Snowflake, moves LAST.** New/changed transforms default off-Snowflake where feasible.

**Goal:** the *active execution* stories for the cost playbook (§6 holds the principles; E11 holds the work). Anchored on cutting **Dagster+ run-minutes + Snowflake credits** by moving the baseball transform/CI onto cheaper substrates — the same lean-lakehouse direction the new sports start on (`sport_data_platform.md`). Pairs with the master-guide cost stories (A2.15/16/17/18, I.5).
> **💰 Concrete payoff (operator 2026-06-18):** E11's Snowflake/Dagster savings are the **budget source for the SportsGameOdds F5 data subscription (E2.0c, ~$179–299/mo)** — landing E11 + the ~100-paying-user milestone is the gate that makes that purchase affordable. So E11 isn't just hygiene; it directly unlocks the F5 value path.

### E11.1 — Migrate the baseball dbt project onto the lean lakehouse (S3 + dbt-duckdb on Railway)  ⬜  **[cost · careful: baseball is LIVE]**
**Why:** MLB's bill is **frequency × full-rebuild on Snowflake** (A2.15/16) + **Dagster+ run-minutes**. The `sport_data_platform.md` pattern — **S3 Parquet lake + `dbt-duckdb` run in a Railway container, IAM credential chain, Dagster only coordinating** — is exactly what we're standing up for NFL/NCAAB/NCAAF. Migrating baseball onto it consolidates to **one cheap substrate** and removes the warehouse from the transform path. This is the inverse of NFL's brownfield migration: NFL is *stale* brownfield (re-pull freely); **baseball is LIVE brownfield — migrate behind value-preserving diffs, never big-bang the serving path.**
**Tasks:**
- [ ] **Audit & classify** every baseball dbt model: movable to `dbt-duckdb`-over-S3 vs must-stay-Snowflake (anything on the live intraday predict/serving path, or needing Snowflake-only features). Land raw/marts as Parquet in the I.2 S3 bucket; `dbt-duckdb` reads S3 (credential chain).
- [ ] **Run dbt in a Railway container** (not Dagster+ run-minutes); Dagster only triggers/sequences (event-driven), per §6.
- [ ] **Migrate in waves, heaviest + least-serving-coupled first** — the Tier-3 Statcast batch marts are the natural first wave (the A2.17 DuckDB pilot). The live predict/serving path moves **last**, and only once its read path is repointed (A2.17 Phase 2 caveat) — or stays on Snowflake if the cost there is already negligible.
- [ ] **Value-preserving:** grain + fingerprint diff (`COUNT(*)`/`COUNT(DISTINCT key)`/`ROUND(SUM(<float>),3)`) before vs after for every migrated model (mirror the A2.10/A2.11 validations); zero model-output change.
- [ ] Keep **incremental + batch** discipline + the weekly full-refresh safety net; preserve leakage guards.
- [ ] Coordinate with **E11.2** (state-aware builds) and the master A2.17 DuckDB pilot — same substrate.
**AC:** a documented model-by-model migration plan; the heavy non-serving marts running on `dbt-duckdb`/S3 with a **measured Snowflake-credit + Dagster-run-minute reduction** (cross-check at the next spend re-audit); every migrated model value-preserving; the live serving path unbroken throughout.
```
▶ New-session prompt — Story E11.1 (baseball dbt → lean lakehouse)
Read: sport_data_platform.md (the target architecture) + §6 here + master implementation_guide.md A2.15/16/17
(the spend audit + DuckDB pilot) + baseball_data_mart_inventory.md (the model catalog).
Migrate the baseball dbt transform onto S3-Parquet + dbt-duckdb-in-a-Railway-container, Dagster coordinating
only. WAVE 1 = the heavy Tier-3 Statcast batch marts (least serving-coupled; the A2.17 pilot). VALUE-PRESERVING:
grain+fingerprint diff before/after each model (A2.10/A2.11 pattern); zero output change. LIVE serving/predict
path moves LAST and only after its read is repointed — do NOT big-bang it. Keep incremental + weekly full-refresh
safety net. Measure Snowflake-credit + Dagster-run-minute deltas. Conventions: dbtf not dbt; Snowflake via MCP
fully-qualified no USE; uv run python; IAM/credential-chain for S3; do not git commit/push.
```

### E11.2 — State-aware dbt builds (`state:modified+` / `source_status:fresher+`)  ✅  **[migrated from master Story I.5 · CODE-COMPLETE 2026-06-19]**
**Goal:** build only what changed, on both paths — **CI** (`state:modified+`, code diff) and **daily Dagster** (`source_status:fresher+`, data diff). Both hinge on a **reliable persisted state artifact** (`manifest.json`/`sources.json`).
**Status:** Both tasks complete. Task 1 SHIPPED 2026-06-15; Task 2 CODE-COMPLETE 2026-06-19.
**Tasks:**
- [x] **Task 1 validation (post-bootstrap):** confirm a PR touching one leaf model builds ~1–3 models in CI, not 117.
- [x] **Task 2 (CODE-COMPLETE 2026-06-19):** Added `freshness`/`loaded_at_field` to 11 high-volume source tables (parlayapi ×5, oddsapi ×3, statsapi.weather_raw, actionnetwork.public_betting_raw, savant.catcher_framing_raw + sprint_speed_raw + statsapi clusters); modified `services/dbt_runner/server.py` to download prior state from `s3://baseball-betting-ml-artifacts/dbt_state/{env}/` before the build and upload `manifest.json`+`sources.json` after; `dbt_daily_build` op now passes `use_state=True` on "run" days (the majority of days); full-build fallback when state is absent (first run or upload failure). Sunday full-refresh and midweek build days always rebuild the full DAG.
- [x] dbt-fusion `source_status` + `--state` assumed supported (same mechanism as the working `state:modified+` in CI). If the selector is rejected at first run, the server falls back to the original full-build args (returncode != 0 → no state upload → next run is also full, so the failure mode is cost-neutral not data-corrupting).
**AC:** CI builds only the modified subtree per PR; the daily op rebuilds only descendants of fresher sources; weekly full build remains the safety net; measured credit reduction expected at the 2026-06-22 re-audit.
**Operator steps:** deploy the dbt-runner Railway service (adds `boto3` to requirements; set `DBT_STATE_BUCKET=baseball-betting-ml-artifacts`, `DBT_STATE_PREFIX=dbt_state`, `TARGET_ENV=prod` in Railway env vars). First prod run will full-build (no prior state) and upload the initial `manifest.json`+`sources.json`; subsequent runs use `source_status:fresher+`.
**Caveat:** `source_status:fresher+` selects by *source* freshness, so logic-only changes are covered by CI's `state:modified+` + the weekly full build, not the daily path. *(Full original spec + prompt: master `implementation_guide.md` Story I.5.)*

### E11.0 — Dockerized dbt runner on Railway/EC2 (the execution substrate)  ✅  **[⭐ CODE-COMPLETE 2026-06-19 · foundational cost piece · prerequisite for E11.1]**
**Why (operator 2026-06-18):** today dbt runs inside Dagster ops → Dagster's metered compute. The `sport_data_platform.md` target (and what NFL/NCAAB/NCAAF will start on) is **dbt running in its own container on Railway (or EC2-batch), with Dagster only triggering/coordinating.** We don't have that substrate yet — standing it up (a) cuts Dagster run-minutes by moving dbt execution off Dagster, and (b) is the environment E11.1's dbt-duckdb migration runs in.
**Tasks:**
- [x] **Containerize:** `services/dbt_runner/` — `Dockerfile` (python:3.12-slim, dbt-fusion via curl install script, `dbt/` project baked in); `entrypoint.sh` (Snowflake key PEM→file, uvicorn); `railway.toml` (always-on web service, `restartPolicyType = "ON_FAILURE"`); `requirements.txt`.
- [x] **HTTP service:** `services/dbt_runner/server.py` — FastAPI, POST `/run` (returns `run_id`, 409 if concurrent), GET `/status/{run_id}`, Bearer auth (`DBT_RUNNER_AUTH_TOKEN`), background thread execution of `dbtf`, in-memory run store.
- [x] **Dagster dispatch:** `DbtRunnerResource` (`pipeline/resources/dbt_runner_resource.py`) — `ConfigurableResource`, polls `/status` with configurable interval/timeout, streams logs back; `_run_dbt()` in both ops files checks `DBT_RUNNER_URL` → remote when set, in-process fallback when not.
- [x] **dbt-fusion manifest fix:** `pipeline/assets/dbt_assets.py` `_manifest_dict()` strips `operation.*` nodes from `nodes`+`parent_map`+`child_map` before passing to `@dbt_assets` (dagster-dbt crashes on `operation.*` nodes because `config=None`).
- [x] **Tests:** `betting_ml/tests/test_dbt_runner.py` — 13 tests across `DbtRunnerResource`, `_run_dbt_remote` (both ops), and `server._execute`; `patch.object(mod.attr)` avoids `pipeline/__init__.py` credential chain.
**AC:** the baseball dbt build runs in the container with Dagster only coordinating; a measured Dagster run-minute reduction; the substrate is reusable for the new sports (same pattern). **Deps:** none (foundational); **unblocks E11.1.**
**Operator deploy steps (post-Railway provision):** (1) set `DBT_RUNNER_URL=https://<service>.railway.app` + `DBT_RUNNER_AUTH_TOKEN=<secret>` in Dagster+ env vars; (2) validate with one intraday op (e.g. `odds_snapshot_dbt_rebuild`) and confirm the Dagster+ run-minute is shorter; (3) watch `/status/{run_id}` polling logs confirm completion.
```
▶ Story prompt — E11.0 Dockerized dbt runner on Railway/EC2   [Infra · cost · ⭐ foundational]
Read: §5H E11.0 + sport_data_platform.md (target arch) + §6 + services/odds_capture + services/derivative_capture (the Railway-cron container pattern to mirror) + the current Dagster dbt op(s).
Do: containerize the baseball dbt project (dbt-fusion/dbt-duckdb + IAM/credential-chain for S3+Snowflake); deploy to Railway (or EC2-batch); switch Dagster from running dbt in-process to TRIGGERING the container (event-driven) + streaming status back. Validate model parity + measure the Dagster run-minute drop. EVAL/CLV discipline unaffected.
Gate/AC: dbt runs in the container, Dagster only coordinates; measured Dagster reduction; reusable substrate for new sports. Unblocks E11.1.
Closeout (per §0.1): CI green + ⏭️ Operator handoff (deploy steps + git add + what to verify).
```

### E11.3 — Query/job cost tagging (Snowflake `QUERY_TAG` + Dagster op tags)  ✅  **[⭐ cost observability · COMPLETE 2026-06-19]**
**Why (operator 2026-06-18):** the bill is currently one opaque number per provider. Tagging every query/op by the job that ran it turns "Snowflake = $359" into "job X = $N" — which makes the 6/22 audit and *every* cost lever measurable (and tells us where to migrate next). Cheap; do it first.
**Tasks:**
- [x] **Snowflake `QUERY_TAG`** per dbt run/model — `on-run-start` in `dbt_project.yml` sets `QUERY_TAG = 'DBT_JOB_NAME|TARGET_ENV|invocation_id'`; `query-comment` embeds model name in SQL text; Dagster `_run_dbt()` helpers inject `DBT_JOB_NAME=context.job_name`.
- [x] **Non-dbt ops** tagged — `check_games_today`, `_query_slate` (odds_current_rebuild_sensor) both use `session_parameters={"QUERY_TAG": ...}`; `_run_script()` in both ops files injects `DAGSTER_JOB_NAME=context.job_name` so scripts using `get_snowflake_connection()` (22+ scripts) and `write_serving_store._sf_connect()` are auto-tagged.
- [x] **Cost-by-job view** — `scripts/ops/snowflake_cost_by_job.py`: queries `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, estimates compute credits (execution_ms / 3_600_000 × credits/hr by warehouse size), ranks by estimated total credits; `--raw` for CSV.
**AC:** every job's Snowflake queries carry a `QUERY_TAG`; a cost-by-job breakdown exists (Snowflake credits per tag) and pairs with the Dagster usage-by-job export; the 6/22 audit uses it. **Deps:** none.
```
▶ Story prompt — E11.3 Query/job cost tagging   [Infra · cost · ⭐ do first]
Read: §5H E11.3 + §6 + the dbt project config + Snowflake ACCOUNT_USAGE.QUERY_HISTORY.
Do: set Snowflake QUERY_TAG per dbt run/model (dbt query_tag/query-comment with job+model+env) + tag non-dbt op queries; add Dagster op tags; build a cost-by-job view (credits per query_tag from QUERY_HISTORY) + pair with the Dagster usage-by-job export.
Gate/AC: queries tagged by job; a cost-by-job breakdown exists and feeds the 6/22 audit. Cheap, low-risk.
Closeout (per §0.1): CI green + ⏭️ Operator handoff (+ git add).
```

### E11.4 — Decompose the intraday polling jobs (python→crons, dbt→E11.0)  ⬜  **[⭐ the single biggest Dagster lever — from the 6/2026 usage data]**
**Why (6/2026 Dagster usage + operator note):** **`lineup_monitor_job` (24%) + `odds_snapshot_job` (21%) + `intraday_schedule_job` (20%) = ~65% of all Dagster usage.** They're frequency-driven AND **each bundles both python scripts *and* dbt jobs in-op — the embedded dbt is part of why the run times are long** (operator). §6: Dagster *coordinates*, Railway/cron + the dbt container *execute*. So this isn't a simple "move the poller" — **decompose** each job: the polling/python part → a cheap Railway cron; the dbt part → the **E11.0 dbt container** (off Dagster's metered compute). That's the largest single Dagster reduction available.
**Tasks:**
- [ ] **Split each job into its parts:** python polling/snapshot vs the dbt build(s) it triggers in-op.
- [ ] Re-home the **python/polling** part of `lineup_monitor` / `odds_snapshot` / `intraday_schedule` (and `intraday_weather`, 7%) as **Railway cron services** (mirror `services/odds_capture` / `services/derivative_capture`); preserve cadence + leakage-safe snapshot timestamps + the PG/Snowflake landing.
- [ ] Route the **dbt** part to the **E11.0 container** (Dagster triggers it, doesn't run it in-process). *(Depends on E11.0.)*
- [ ] Dagster keeps only **coordination/trigger** + genuine batch/ML ops; no python-poll-loops or in-op dbt in metered ops.
- [ ] Validate data continuity (no gaps in lineups/odds/weather) + measure the Dagster usage drop.
**AC:** the intraday jobs no longer run python-polling or dbt on Dagster's metered compute (python → crons, dbt → E11.0); data continuity preserved; measured Dagster usage reduction (target: the bulk of the ~65%). **Deps:** the Railway cron pattern (exists) + **E11.0** (for the dbt half).
```
▶ Story prompt — E11.4 Offload intraday polling jobs → Railway crons   [Infra · cost · ⭐ biggest Dagster lever]
Read: §5H E11.4 + the 6/2026 Dagster usage-by-job data (lineup_monitor 24% + odds_snapshot 21% + intraday_schedule 20% = ~65%) + services/odds_capture + services/derivative_capture (the Railway cron pattern) + the current Dagster definitions for those jobs.
Do: re-home lineup_monitor / odds_snapshot / intraday_schedule (+ intraday_weather) as Railway cron services (mirror odds_capture); preserve cadence + leakage-safe timestamps + landing; Dagster keeps only coordination + real batch/ML ops. Validate no data gaps + measure the Dagster drop.
Gate/AC: polling jobs on Railway crons (not Dagster); data continuity intact; measured Dagster usage reduction.
Closeout (per §0.1): CI green + ⏭️ Operator handoff (deploy + git add + verify no lineup/odds/weather gaps).
```

---

## 5I. Epic E12 — Serving Parity / Point-in-Time Serving Completeness  🟢 **STRUCTURAL AC MET 2026-06-19 (live-sparse parity PASS); live-skill forward-validation accumulating**  **[⭐ the live-performance lever · converted from master Story 30.3]**

> **E12 operator run — PASS (2026-06-19).** Ran the tier-aware harness for the live 2026-06-19 morning slate, which fell back to `data_source=intraday_assembly` (feature-store coverage 0.66 < 0.70) — i.e. a **genuine live-sparse profile, not a dense backfill re-read**, the exact surface 30.3 said understates skew if you re-read a settled date. On the **pre_lineup** serve tier all three targets PASS: total_runs 89/89, run_diff 126/126, home_win 156/156 structurally served; **0 strong-tier features degraded** on every target. The only all-null→const column is `series_game_number` (run_diff + home_win) — a benign scheduling field not reconstructed in the Stats-API fallback assembly, non-strong, doesn't fail parity. ⇒ The point-in-time SERVING-completeness AC ("live served matrix matches the feature-store matrix, no strong-tier NULL/misalignment, column-aligned") is **structurally satisfied** by the 33.0 tier split. **Remaining:** the live-skill half of the AC ("live home_win skill moves toward offline ~0.42") is a forward-validation that accumulates as morning pre_lineup rows settle — track `daily_model_predictions` morning-tier outcomes over time.

> **E12 status (2026-06-19).** **Finding:** there is **no structural train/serve misalignment** — `load_features` (train) and `load_todays_features` (serve) both select `f.*` from the SAME `feature_pregame_game_features` table; the only difference is the `has_full_data` filter. So the skew is **purely point-in-time value-completeness** (sparse pre-game row → dense post-game backfill), exactly the master-30.3 root cause — and the **serve-path FIX already shipped**: Story 33.0 routes the live morning run to a **pre-lineup model** whose contract DROPS the lineup-gated families that are NULL pre-lineup (home_win 211→156 cols, lineup-gated families 32→5), 30.3 defers the actionable edge to the dense post_lineup re-score, 30.13 adds a serve-time freshness gate. **What E12 added this session:** (1) made the parity harness **tier-aware** — it was diffing the sparse morning matrix against the *champion* contract (overstating skew ~30% for a model the morning tier never serves) and now grades the **actually-served** variant, emitting a per-target `parity_ok` + a process **exit code** so it can GATE a serve, not just diagnose; `--champion-shadow` shows why morning routes to pre-lineup. (2) A **standing serving-parity assertion** (`betting_ml/tests/test_serving_parity_guard.py`, 21 tests, no Snowflake) that locks the invariants the fix depends on — pre-lineup ⊆ champion, pre-lineup drops the lineup-gated families, and the pure parity verdict fails on the two live-skill killers (structural-absent + strong-tier flattened). **Operator-pending:** run the tier-aware harness for a live morning slate (the only date with a true sparse profile) to confirm `parity_ok` on the pre-lineup tier, then forward-validate that live home_win skill moves toward offline ~0.42. Files: `betting_ml/scripts/serving_parity_report.py`, `betting_ml/tests/test_serving_parity_guard.py`.

**Why (E1.8 verdict, 2026-06-18):** after E1.7 + E1.8 the *construction* surface is clean, but **the bulk of the offline→live skill collapse (home_win corr 0.42 offline/feature-store → 0.001 live) is point-in-time SERVING SKEW** — strong-tier (lineup-dependent) features arriving **NULL/misaligned at morning `predict_today` serve.** Master Story 30.3 *diagnosed* this (the same model + contract scores 0.42 on the feature-store matrix vs 0.001 on the live served matrix → it's the serve path, not the model). **E12 is the FIX** — and it's plausibly what finally lets the honest offline skill show up live, so it's the highest-value live-performance lever on the model track.
**Tasks:**
- [ ] **Serving-parity harness:** per game, diff the live `predict_today` feature matrix vs the feature-store/training matrix — flag every column that is NULL/imputed/misaligned at serve but populated in training (esp. ELO/archetype/EB/lineup-dependent strong-tier features).
- [ ] **Fix the serve path** so the matrix is point-in-time *complete* at morning serve (or so the model degrades honestly when a feature genuinely isn't available pre-lineup — pairs with the E9.6 pre-lineup theme / master 30.8). Keep the `predict_today` CONTRACT-GUARD (column count/alignment).
- [ ] **Standing check:** a recurring serving-parity assertion so skew can't silently return.
**AC:** the live served matrix matches the feature-store matrix (no strong-tier NULL/misalignment at serve, column-aligned); **live home_win skill moves toward the offline ~0.42** (forward-validated); a standing serving-parity guard. **Deps:** master 30.3 (diagnosis) + `predict_today.py`. **⚠️ Sequencing: E12 runs BEFORE E1.9 (data-first, operator 2026-06-18)** — fixing the serve path makes the E1.9 bake-off's CV predictive of *live* skill, so v6 is selected for what's actually servable (E1.8's gap attribution confirms serving skew, not leakage, is the live bottleneck). *(Full diagnosis: master `implementation_guide.md` Epic 30 / Story 30.3.)*
```
▶ Story prompt — E12 Serving parity / point-in-time serving completeness   [Model-A · correctness · ⭐ the live lever]
Read: edge guide §5I E12 + master implementation_guide.md Epic 30 header + Story 30.3 (the serving-skew diagnosis: same model = 0.42 feature-store vs 0.001 live) + predict_today.py (the live serve path + its CONTRACT-GUARD) + the feature-store/training matrix build + [[project_prod_model_audit_jun2026]].
Do: build a serving-parity harness diffing the live predict_today matrix vs the feature-store/training matrix per game; find the strong-tier (lineup-dependent ELO/archetype/EB) features arriving NULL/misaligned at morning serve; fix the serve path to be point-in-time COMPLETE (or degrade honestly pre-lineup, per 30.8/E9.6); add a standing serving-parity assertion.
Gate/AC: live served matrix matches the feature-store matrix (no strong-tier NULL/misalignment, aligned); live home_win skill moves toward offline ~0.42 (forward-validated); standing guard. Pairs with v6 (E1.9). Promoting fixes shifts live picks → app changelog.
Closeout (per §0.1): CI green + ⏭️ Operator handoff (run-order + git add + forward-validation to verify).
```

---

## 6. Cost playbook (ported + applied to every Edge story)

The platform's bills are **frequency-driven** (intraday ticks × full rebuilds), not per-transform heaviness. The established pattern (Stories A2.12/15/16/17/18): **Dagster coordinates; Railway / EC2-batch / DuckDB / S3-Parquet executes.** Apply these as hard constraints on all Edge work. **This section is the principles; the active execution stories live in Epic E11 (§5H)** — the baseball dbt → lean-lakehouse migration (E11.1) and state-aware dbt builds (E11.2).

### 6.1 The reusable patterns (from the master guide)
- **Railway PG serving (A2.12, ✅):** API reads PG, never Snowflake at request time; Dagster reverse-ETLs precomputed outputs into PG via `write_serving_store.py`. *Edge use:* E2 quantiles, E3/E4 edges land in PG as params, not at-request compute.
- **Offload I/O off Dagster run-minutes (A2.18, ✅):** I/O-bound polling (odds capture) runs on a **flat-cost Railway cron** (`services/odds_capture/`), not per-snapshot Dagster jobs (that was the #1 driver, ~1,044 min/mo). Only the dbt rebuild stays in Dagster, event-driven. *Edge use:* **E3.0 Pinnacle ingest mirrors this exactly** — fetch on Railway cron, rebuild in Dagster.
- **Frequency levers before heaviness (A2.15):** intraday ops use `dbtf run` (models only), tests batched to ≤1×/day; gate rebuilds on actual new data (no-op ticks do nothing); scope CI to PR/merge. *Edge use:* any new intraday op E2–E4 add follows `run`-not-`build` + new-data gating.
- **DuckDB-in-Dagster for heavy batch (A2.17, gated):** replace billed Snowflake CTAS with free in-process DuckDB on **S3-Parquet** for heavy, low-frequency, non-serving transforms (precedent: `betting_ml/utils/training_cache.py`). *Edge use:* **E1.3/E1.4 (CSCV, MDA) and E2 backtests run as S3-Parquet→DuckDB/EC2 batch**, never repeated Snowflake scans. Measure Snowflake-credits-saved vs compute-minutes-added — net only.
- **Runaway guards (A2.16):** global `max_runtime` cap + per-subprocess timeout + run-concurrency caps so a wedged/stacked job can't burn run-minutes. *Edge use:* any new Dagster op declares a timeout + concurrency group.

### 6.2 Per-epic cost stance
| Epic | Where it runs | Constraint |
|------|---------------|-----------|
| E1 | EC2/local batch on S3-Parquet | CSCV/MDA capped; periodic not daily; reports → S3 |
| E2 | daily Dagster op, vectorized | cap copula draws (~10k/game); write params+quantiles to PG, not raw samples |
| E3.0 | Railway cron (fetch) + Dagster (rebuild) | mirror A2.18; flat host ≪ run-minutes |
| E3/E4 | daily pipeline (light) | GBM/NGBoost + arithmetic; no request-time Snowflake |
| E5 | Railway cron (prop fetch) + daily/batch pricing | mirror A2.18; live + full historical backfill fit in 5M/mo; log credit spend |
| E6 | EC2/local batch on S3-Parquet | analytical sweep; reuses E1.3; one-off, not a pipeline |
| E7 | cheap ingestion (Stats API/Savant) + DuckDB/S3 batch for MLEs | large data volume but no per-call billing; don't full-rebuild marts intraday |
| E8 | batch projections → Railway PG | precompute; never request-time compute; reuse E2 machinery |
| E9 | app-repo (Lambda/Vercel) + Railway PG | display/glue on existing payloads; reuse de-vig/EV utils; precompute, no request-time compute |

---

## 7. Roadmap — two concurrent Claude Code sessions

> **Ordered execution backlog → `build_roadmap.md`.** This section is the *dependency/lane logic*; the persisted, prioritized **Model build track + Application build track** (the Trello source-of-truth, baseball-only, windowed now → the MLB All-Star break) live in `build_roadmap.md`. Update that doc as stories ship / requests land.

Lanes are file-disjoint so two sessions never collide. **Session A = models/validation/totals/props-pricing/projections** (`betting_ml/`, `dbt/`, sub-models). **Session B = market models + data ingestion** (`betting_ml/utils` odds, market features, Pinnacle/prop/MiLB ingest). **App stories** (🧩 — E2.7, E5.5, E8.7, E9.x) run in a **separate app-repo session**; per **§0.3** their `▶ App-session prompt` is **emitted by the upstream model session as its final step**, so the app session always starts from an accurate, just-built contract.

```
TIME →

Session A:  E1.1─E1.4─E1.5 ─▶ E6 (feature audit; reuses E1.3) ─▶ E2.1…E2.6 ─▶ E5.2─E5.3─E5.4 ─▶ Fantasy guide F1…F8 (own guide; reuses E2, needs E7 for F4)
            (overfitting; gates go-live)  (feature backlog)     (per-side totals)  (prop pricing,    (projections; E8.4 waits on E7)
                                                                                    builds on E2; E1-gated)

Session B:  E3.0 ─▶ E3.1─E3.2─E4.1─E4.2─E4.3─E3.3─E4.4 ─▶ E2.0 + E5.0─E5.1 (derivative + prop ingest/backfill) ─▶ E7.1─E7.2─E7.3─E7.4─E7.5
            (shared market layer; market models — needs E1.4 only at GO-LIVE)  (plumbing)        (MiLB ingest + MLEs → feeds E8.4)

App lane:   A0.4.34 (CLV bar) ─▶ E2.7 (distribution UX) ─▶ E4.4 book-aware ─▶ E5.5 (prop pages) ─▶ F7 (fantasy surfaces — fantasy guide)
            (after the model side it consumes is serving)
            + E9 (beta-request backlog) runs CONTINUOUSLY in this lane — triage in, build small app stories (e.g. E9.1) or route to the owning epic
```

**Critical-path rules**
1. **E1.4 (PBO/DSR) gates go-live of every E2/E3/E4/E5 betting strategy** — but not their *build*. Sessions build in parallel from day 1; nothing ships live until E1.4 exists and the strategy clears PBO<0.2 + DSR>0. **Strictest for E5 props** (per-market, multiple-comparison-corrected).
2. **E3.0 blocks E3.1 and E4.1** — Session B's first task is always the shared market layer.
3. **E2.5 (leakage-safe backfill) blocks E2.6**; likewise **E5.1 (leakage-safe prop backfill) blocks E5.4**. Can't honestly gate a signal scored in-sample.
3a. **E2.0 (derivative-odds backfill) blocks the E2.6 derivative gate** — it's Session-B data plumbing (shares E5.0/E5.1), runs in parallel with the market-blind E2 model build, but is the long pole for the *derivative* value path. Start it early. (The backfilled odds are eval/CLV-only — never E2 model features.)
4. **E5 spans both lanes:** ingestion (E5.0/E5.1) is plumbing that can start anytime in Session B; pricing (E5.2+) builds on E2's machinery in Session A.
5. **E6 (feature audit) is cheapest right after E1** — reuses E1.3 clustered MDA; run it before sinking time into new features. Output = a backlog of small feature-add stories, each E1-gated.
6. **E7 → Fantasy F4** — prospect projections (fantasy guide F4) need the MiLB MLEs. Fantasy F1/F2 (MLB ROS projections) do **not** need E7 and can start once E2's machinery exists; F4 waits on E7.5.
7. **App lane trails its model dependency:** E2.7 needs E2.3; E4.4 surface needs E4.1; E5.5 needs E5.2/E5.3; E8.7 needs E8.1; A0.4.34 is buildable now.
8. **App-prompt handoff (§0.3):** an app story (🧩) is not "ready" until the upstream model session has run its **final step** and written that story's `▶ App-session prompt` into the guide. The app session never starts from a `⏳`-placeholder prompt — if it's still a placeholder, the upstream work isn't done.
9. **No two sessions edit `betting_ml/utils/promotion_gate*.py` at once** — E1 owns it; everything else only *calls* `evaluate_promotion`.

**Suggested first move:** Session A → E1 validation runs (already code-complete) then E6 (feature audit); Session B → E3.0. **Prop ingestion (E5.0) and MiLB ingest (E7.1) are pure plumbing** that slot into either lane's slack — and per §7A, front-loading E7 is the highest-value use of that slack.

---

## 7A. B2C value lens — market SWOT + priority reframe

§7 optimizes *engineering* parallelism. This section asks the different question you raised: from a **B2C revenue + defensibility** view, where is the highest value — and does that change priorities?

**Market SWOT — Credence as a consumer product (mid-2026):**

| | |
|---|---|
| **Strengths** | Rigorous, distributional, leakage-safe modeling far beyond typical pick/tout sites. Radical transparency / honest framing (no fake win-rates) — rare and trust-building. Live product + serving infra already built (app, player pages, Railway PG, decision-layer surfaces). Deep player-level modeling → natural fit for props (E5) + projections (E8). Advisory posture sidesteps book/auto-bet legal & operational burden. |
| **Weaknesses** | No demonstrated game-betting edge yet — a "beat the market" pitch is unsupported until E3/E4/E5 clear the gates. Betting-advisory market is crowded, trust-eroded, results-chasing churn is high, CAC hard. Any betting edge (props/sharp-anchor) may be thin in coverage and capped by soft-book limits → revenue ceiling. Small team, cost-constrained infra. |
| **Opportunities** | **Dynasty fantasy is underdeveloped** — few tools offer distributional, prospect-aware, multi-year projections; the MiLB-MLE prospect angle (E7→E8) is a moat competitors skip. Distribution-first / transparency-first brand is differentiated. Props volume is exploding and the market is soft → high demand *if* edge is real. One player-modeling spine → bet advisory + props + fantasy: cross-sell + subscription bundling. |
| **Threats** | US sports-betting regulatory / ad / payment-processor flux. Soft books limit winners → undercuts any betting-edge value at scale. Incumbent fantasy/projection brands (FanGraphs/ZiPS, Steamer, FantasyPros, RotoWire) with data + audience. Category trust erosion from pick-sellers tars everyone. Data-source dependency (Odds API, Stats API, Savant) pricing/access risk. |

**The value read.** The betting-edge tracks (E2–E5) are worth building — cheap to validate, product already live — but their revenue is *uncertain, capped, slow to prove, and exposed to limits + regulation*. By contrast, the **fantasy/Dynasty projections vertical (E8, fed by E7)**:

- addresses a genuinely **underserved** niche with weaker incumbents at the Dynasty/prospect end;
- is **not gated on beating an efficient market** — "match or beat ZiPS/Steamer" is an achievable, defensible bar;
- monetizes via **subscription** rather than fickle betting outcomes (better retention, lower churn);
- reuses the **same modeling spine** (low marginal build cost); and
- has a **structural moat** in MiLB-MLE prospect projections few competitors invest in.

So on pure expected-value-and-defensibility, **E8 (fantasy/Dynasty projections) is plausibly the program's highest-value B2C bet** — despite sitting last in the engineering dependency order.

**Priority reframe (what this changes — without abandoning betting):**
1. **Pull E7 (MiLB ingestion) forward** as early parallel plumbing — it's cheap, blocks nothing, and unlocks the highest-value vertical. Don't leave it for "last."
2. **Treat E2–E5 as "prove-it-cheaply, monetize-if-real"** — build + validate at low cost (E5 props is the highest-demand betting feature and reuses live infra), but don't bet the business on a betting edge surviving the gates.
3. **Resource E8 as a strategic vertical, not an afterthought.** Once E2's machinery + E7's data exist, the projections suite is the most likely durable B2C revenue — that's where a second session's time compounds.

Net value-weighted sequence: keep **E1 (done) + E6 (cheap audit) + E2 (the shared distributional machinery)** on the critical path; run **E5 props + E3/E4 market models** as low-cost validation bets; and **start E7 MiLB ingestion early so E8 can become the flagship B2C product** as soon as the machinery is ready.

---

## 8. Definition of done (program level)
Not "we beat Bovada's closing total." Realistically, within ~12 months:
- A **per-side distribution** pricing F5/team-totals/alt-lines with overfitting-audited edge in softer markets (E2 + E1).
- A **closing-line model** with demonstrated positive forward CLV — the leading indicator real edge exists (E3).
- A **book-aware sharp-anchor advisory** that flags when a user's book lags Pinnacle, selectively, DSR>0 (E4).
- **Player-prop projections** on the player pages, with overfitting-audited edge in the soft prop markets where our player-modeling depth pays off (E5).
- A **trustworthy PBO/DSR** on every claimed edge (E1), so "we're getting closer" is measured, not hoped.
- A **validated feature backlog** from a one-time full-surface audit, with the dead weight pruned (E6).
- **Minor-league data + MLEs** closing the rookie-prior gap for the betting models and powering prospect projections (E7).
- A **fantasy/Dynasty projections suite** (distributional, multi-year, prospect-aware) matching or beating ZiPS/Steamer — the program's highest-value standalone B2C vertical (E8, see §7A).
- A **closed beta-feedback loop** (E9): requests captured, triaged, and shipped or routed — incl. the migrated A0 app/infra stories (auth, billing, push, onboarding) and the paid-tier revenue path (E9.7→E9.8).
- An **honest parlay tool** (E10): a calculator that tells users the truth about any parlay now, with a recommender gated behind a real edge source — differentiation that doesn't require beating the market.
- All of it surfaced honestly in Credence as transparency/confidence — never a win-rate claim.

---

## 9. Per-story prompts (standalone sessions)

The full per-story prompt catalog — a `▶ Story prompt` for **every not-yet-completed story** across E1–E11 — lives in **`story_prompts.md`** (same folder); **Fantasy F1–F8 prompts live in `../fantasy/story_prompts.md`** with that vertical. Pull a story's block from there to run it standalone (per §0.4). App surfaces marked **⏳ §0.3** are generated by their upstream model session, not hand-authored. New stories should also embed their `▶ Story prompt` inline with the story.


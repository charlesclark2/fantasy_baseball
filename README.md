# Baseball Betting & Fantasy

ML system for predicting MLB game outcomes (total runs, run differential, win probability) using Statcast pitch data, confirmed batting lineups, starting pitcher profiles, bullpen context, and ballpark factors.

See [`project_context.md`](project_context.md) for the full architecture reference, data source documentation, model inventory, and roadmap.

---

## Current Status

**Phases 1–7 are complete as of 2026-05-05.** The active phase is **Phase 8 — Advanced Feature Engineering + Infrastructure Hardening.**

Phase 7 retrained the v0 baseline into the production v1/v2 set: home_win v1 (Platt-calibrated, ECE 0.0370), total_runs v2 (NGBoost Normal, MAE 3.35), run_differential v1. Card 8.S CLV baseline is `mean_clv +0.0027`, `pct_positive 38.3%` over 91.2% game coverage — the model is at break-even, not yet beating the market. Phase 8 has shipped a large round of new features that the production model has not yet been trained against; Card 8.W (Phase 8 Batch Retrain & Re-evaluation) is the gate that lets those features into the model and unblocks the Wave 5 Bayesian / inference-wrapper cards (8.F1–8.F5).

**Phase 8 cards complete:** 8.A–8.E (pct-diff encoding, ZiPS FIP, OAA, Elo, bat tracking matchup), 8.H3 (live monitoring), 8.I1 (dbt compilation gate), 8.J (pitcher-batter H2H), 8.K (catcher framing), 8.L (bullpen handedness), 8.M (starter arsenal drift), 8.Q (starter CSW%), 8.R (Action Network public betting), 8.S (CLV tracking), 8.T (bookmaker disagreement), 8.U (bullpen leverage exhaustion), 8.X (pythagorean residual), 8.Y (base-state-split metrics).

**Phase 8 cards remaining:** 8.N (time-decay weighting), 8.O (rolling calibration), 8.P (quantile total_runs), 8.V (correlation-aware sizing), 8.W (batch retrain), 8.F1–8.F5 (Bayesian engine — gated on 8.W).

| Domain | Status |
|---|---|
| Pitch physics and outcomes | Complete |
| Game context and results | Complete |
| Player rolling performance (batter + pitcher) | Complete |
| Team rolling offense, pitching, and splits | Complete |
| Starting pitcher game log | Complete |
| Bullpen workload and effectiveness | Complete — base + handedness splits (8.L) + leverage exhaustion (8.U) |
| Confirmed batting lineups (staging) | Complete — 100% coverage 2015–present |
| Probable starting pitchers (staging) | Complete — 97–100% coverage for completed seasons |
| Ballpark context and run factors | Complete |
| Weather (Phase 7) | Complete — temp / wind component / humidity ingested + backfilled 2021+ |
| FanGraphs Stuff+ and ZiPS (Phase 7) | Complete — pre-season ZiPS + in-season Stuff+ rolling windows |
| Umpire tendencies (Phase 7) | Complete — 99.4% coverage for 2026 regular season |
| Injury / IL tracking (Phase 7) | Complete — 66,497 transactions 2021–2026; injury-adjusted lineup wOBA |
| Pitcher / batter clustering + H2H (Phase 7 + 8.J) | Complete — archetype matchup features + per-pair Bayesian-shrunk H2H wOBA / xwOBA |
| Catcher framing (8.K) | Complete — blended framing + defensive runs ≥99.8% coverage |
| Defensive fielding OAA (8.C) | Complete — 2016–2026 ingested via `ingest_oaa.py` |
| Elo team strength (8.D) | Complete — `team_elo_history`; `elo_diff` is 4th-strongest feature (`|r|=0.1854`) |
| Bookmaker disagreement (8.T) | Complete — 7 columns from morning-snapshot dispersion across sharp/soft tiers |
| Action Network public betting (8.R) | Complete (2026-05-08) — 6,439 rows backfilled (2024–2026; API empty for 2021–2023); 99.1% game-matching on 2025; sum check 100.001 |
| Betting odds (staging + mart) | Events backfilled 2021–present; odds prices: 2023 partial + live 2026 |
| ML feature store | Complete — every Phase 8 column wired into `feature_pregame_game_features`; production models do not yet consume them (gated on 8.W) |
| EDA | Complete (Phase 3, 2026-04-24) — 7 Marimo notebooks |
| ML pipeline + models (production) | Phase 7 v1/v2 baseline — home_win v1 ECE 0.0370, total_runs v2 MAE 3.35, run_differential v1; per-target version tags supported |
| Model versioning + prediction CLI | Complete (Phase 7) — independent per-target promotion; data_source tagging (`feature_store` vs. `intraday_fallback`) |
| Betting application layer | Complete (Phase 6, 2026-05-01) — Diamond Edge Streamlit app: Today's Picks, Market Comparison, EV Tracker, Model Performance (now with CLV section) |
| Model quality / market edge | Break-even: CLV +0.0027 mean / 38.3% positive over 91.2% coverage. 8.W batch retrain is the gate to evaluate whether Phase 8 features unlock positive edge. |

---

## Repo Structure

```
├── app/                        # Diamond Edge — Streamlit application (Phase 6)
│   ├── streamlit_app.py        # st.navigation() dispatcher; app entry point
│   ├── home.py                 # Landing page: description, nav guide, model fact sheet, pipeline diagram
│   ├── utils/
│   │   └── db.py               # Snowflake session factory (cached)
│   └── pages/
│       ├── 1_Today_Picks.py    # Today's picks table + market movement expander
│       ├── 2_Market_Comparison.py  # Line movement, totals chart, bookmaker deep-dive
│       ├── 3_EV_Kelly.py       # All Markets EV table + Kelly Suggested Slate + interactive sizing
│       └── 4_Model_Performance.py  # Brier trend, CLV chart, P&L simulation, summary metrics
├── dbt/                        # dbt-fusion project (all SQL transforms)
│   ├── models/
│   │   ├── staging/            # Type-cast and normalize raw sources (6 models)
│   │   ├── mart/               # Feature-domain mart tables (22 models)
│   │   └── feature/            # Pre-game feature assembly — Phase 2 complete (6 models)
│   └── seeds/                  # ref_teams static reference
├── scripts/                    # Python ingestion + prediction scripts
│   ├── savant_ingestion.py     # Baseball Savant (Statcast) — daily
│   ├── ingest_statsapi.py      # MLB Stats API schedule + venues
│   ├── odds_api_ingestion.py   # The Odds API events + odds
│   ├── predict_today.py        # Pre-game prediction CLI — scores all confirmed games
│   ├── backfill_prediction_log.py  # Backfills actual_outcome + closing_market_prob (CLV) into prediction_log
│   ├── daily_run.md            # Step-by-step daily runbook (ingestion + prediction)
│   └── date_utils.py           # UTC date helpers (used by odds ingestion)
├── .github/workflows/          # GitHub Actions CI/CD
│   ├── daily_ingestion.yml     # Cron 08:00 EDT — ingest → dbt-build → backfill (3-job chain)
│   ├── dbt_daily_build.yml     # Reusable workflow — odd=build, even=run, Sunday=full-refresh
│   ├── lineup_monitor.yml      # Hourly — re-ingest Stats API + detect confirmed lineups
│   ├── odds_snapshot.yml       # 13:00/18:00/23:00 EDT — intraday odds re-ingestion
│   └── dbt_staging_build.yml   # workflow_dispatch — lineup-scoped dbt build (game_pk input)
├── data_quality/
│   ├── open_data_quality_issues.md           # Unresolved issues
│   ├── resolved_data_quality_issues_april_2026.md
│   └── data_availability_windows.md          # Verified feature availability dates
├── exploratory_data_analysis/  # EDA notebooks (Phase 3, Marimo)
│   ├── 01_target_variables.py  # Target distributions; era shift; baseline MAE
│   ├── 02_feature_coverage.py  # Null rate heatmap; imputation decisions
│   ├── 03_rolling_window_stability.py  # Window size effect; early-season instability
│   ├── 04_feature_correlations.py      # Pearson/Spearman correlations; multicollinearity
│   ├── 05_park_and_context.py          # Park factors; schedule fatigue; OLS R² comparison
│   ├── 06_bat_tracking_era.py          # Bat tracking signal; single-model verdict
│   ├── 07_engineered_feature_lift.py   # Delta/momentum and handedness lift validation
│   └── betting_model_findings.md       # Cumulative EDA findings (sections 01–09)
├── betting_ml/                 # ML model code (Phase 4+)
│   ├── utils/
│   │   ├── data_loader.py      # Snowflake → pandas; load_features() with has_full_data + games_played filters
│   │   ├── cv_splits.py        # Temporal leave-one-season-out CV splits
│   │   ├── preprocessing.py    # Imputation + Bayesian shrinkage pipeline
│   │   ├── feature_selection.py # load_retained_features() — canonical 241-feature list
│   │   ├── model_io.py         # save_model / load_model via joblib
│   │   ├── evaluation.py       # fold_metrics, brier_score_over_under helpers
│   │   └── probability_layer.py # compute_posterior(), compute_edge(), compute_kelly()
│   ├── models/
│   │   ├── total_runs_trainer.py   # train_ridge, train_xgboost, train_ngboost, p_over_line
│   │   ├── win_outcome_trainer.py  # train_logistic, train_xgboost_classifier, compute_ece
│   │   ├── total_runs/             # Serialized total runs models
│   │   ├── run_differential/       # Serialized run differential models
│   │   └── home_win/               # Serialized win outcome models
│   ├── scripts/
│   │   ├── train_total_runs_baselines.py        # Card 4.9: train all total runs baselines
│   │   ├── train_run_diff_baselines.py          # Card 4.10: train all run diff baselines
│   │   ├── train_win_outcome_baselines.py       # Card 4.11: train win outcome baselines
│   │   ├── run_hyperparameter_search.py         # Card 4.12: Optuna search (USER-EXECUTED)
│   │   ├── run_probability_layer.py             # Card 4.13: Bayesian probability layer + alpha tuning
│   │   ├── generate_tuning_report.py            # Card 4.12: report from tuning_results.json
│   │   ├── analyze_pitching_decomp.py           # Card 3.8: bullpen vs. starter decomposition
│   │   └── analyze_home_away_pitch_asymmetry.py # Card 3.9: home/away pitching asymmetry
│   ├── evaluation/             # Results: JSON + markdown reports per card
│   │   └── postmortem_v0.md    # Phase 6 post-mortem findings (Card 6.H)
│   └── tests/
│       ├── test_cv_splits.py
│       └── test_preprocessing.py
├── plan_specs/                 # Declarative PlanSpec YAML files for agentic execution
│   ├── phase_3/                # EDA analysis cards (3.8–3.11)
│   ├── phase_4/                # ML pipeline cards (4.6–4.13)
│   ├── phase_6/                # Betting application cards (6.B–6.I) — complete
│   ├── phase_7/                # Model refinement + production infra — complete
│   └── phase_8/                # Advanced feature engineering + infra hardening (active)
│       # A–E, H3, I1, J–U, R complete; N/O/P/V remain; W (batch retrain) gates Wave 5 (8.F1–8.F5)
├── model_registry.yaml         # Canonical _prod model artifacts for all three targets
├── .mcp.json                   # Snowflake MCP server config for Claude Code
├── snowflake_mcp_config.yaml   # MCP service permissions (read-only)
└── project_context.md          # Full architecture, data sources, roadmap
```

---

## Daily Pipeline

Ingestion and transformation run automatically via GitHub Actions — no manual steps required during the season.

| Workflow | Schedule | What it does |
|---|---|---|
| `daily_ingestion.yml` | 08:00 EDT (cron) | Ingests Statcast + Stats API + Odds API, then chains `dbt_daily_build.yml`, then runs `backfill_prediction_log.py` |
| `dbt_daily_build.yml` | Called by `daily_ingestion.yml` or manually | `dbt build` (odd days), `dbt run` (even days), `dbt build --full-refresh` (Sundays) |
| `lineup_monitor.yml` | Every hour (cron) | Re-ingests Stats API schedule; detects newly confirmed lineups; conditionally rebuilds lineup feature models |
| `odds_snapshot.yml` | 13:00 / 18:00 / 23:00 EDT | Intraday odds re-ingestion on game days (skips off-days) |
| `dbt_staging_build.yml` | `workflow_dispatch` (game_pk input) | Lineup-scoped `dbt build --select +stg_statsapi_lineups+` dispatched by Snowflake lineup monitor |

For ad-hoc backfills or manual reruns, see [`scripts/daily_run.md`](scripts/daily_run.md).

```bash
# Ad-hoc: run ingestion manually (auto-detects gap from last loaded date)
cd scripts/
uv run savant_ingestion.py batter_pitches
uv run ingest_statsapi.py schedule
uv run odds_api_ingestion.py events && uv run odds_api_ingestion.py odds

# Ad-hoc: rebuild dbt models
dbtf build

# Ad-hoc: run today's predictions
uv run predict_today.py
```

---

## Diamond Edge App

The Phase 6 Streamlit app (`app/`) is the primary interface for daily betting analysis.

```bash
streamlit run app/streamlit_app.py
```

| Page | Description |
|---|---|
| 🏠 Home | Project overview, model fact sheet, pipeline diagram |
| ⚾ Today's Picks | Model predictions for all confirmed games; market movement expander |
| 📊 Market Comparison | Line movement chart, totals chart, bookmaker deep-dive |
| 💰 EV Tracker | All Markets EV table + Kelly Suggested Slate with interactive bet sizing |
| 📈 Model Performance | Brier score trend, CLV chart, cumulative P&L simulation |

---

## Data Sources

| Source | Coverage | Notes |
|---|---|---|
| Baseball Savant (Statcast) | 2015-04-05 – present | ~7.5M pitches; updated daily |
| MLB Stats API schedule | 2015 – present | Lineups + probable pitchers via `monthly_schedule` JSON |
| MLB Stats API venues | All active parks | Field dimensions, surface, roof, elevation |
| MLB Stats API transactions | 2021 – present | 66,497 IL placements / activations / reinstatements |
| The Odds API | 2021 regular season – present | Events backfilled 2021–present; odds prices: 2023 partial + live 2026 |
| FanGraphs (Stuff+, ZiPS, hitting leaderboard, catcher framing) | 2020 – present | Daily / weekly / preseason cadence per leaderboard |
| Baseball Savant OAA / DRS | 2016 – present | Team-season fielding aggregates |
| UmpScorecards + MLB Stats API umpire feed | 2018 – present | HP umpire tendency z-scores + daily assignments |
| Open-Meteo (weather) | 2021 – present | Temp / wind component / humidity at first pitch for outdoor parks |
| Action Network public betting | 2021+ (sparse early seasons) – present | Public money% / ticket% for ML and totals; ingested via `ingest_actionnetwork_betting.py` |

Key data availability notes (verified against actual row counts — see [`data_quality/data_availability_windows.md`](data_quality/data_availability_windows.md)):
- **Bat tracking** (`bat_speed`, `swing_length`, `attack_angle`, `attack_direction`, `swing_path_tilt`): 2023-07-14+, swing events only (~45% of pitches)
- **Intercept offset**: 2023-07-14+, same coverage as bat tracking
- **`hyper_speed`**: 2015+ (~33% of pitches; batted contact events; distinct from the 2023 bat tracking system)
- **Confirmed lineups**: 100% for all completed regular season games 2015–present

---

## Tech Stack

| Layer | Tool |
|---|---|
| Data warehouse | Snowflake (`baseball_data` database) |
| Transforms | dbt-fusion (`dbtf`) — use `dbtf`, not `dbt` |
| Ingestion | Python + `uv` |
| ML (planned) | Python / XGBoost (`betting_ml/`) |
| EDA | Marimo (`exploratory_data_analysis/`) |
| Claude Code data access | Snowflake MCP server (`snowflake-labs-mcp`) |

---

## dbt MCP Server (Claude Code)

The repo includes a dbt MCP server so Claude Code can introspect the dbt project — list models, retrieve column descriptions, and trace lineage — without reading schema.yml manually.

**Setup** — activates automatically when Claude Code loads this project. No additional install step needed; `uvx` pulls `dbt-mcp` on first run.

**Compatibility** — standard `dbt` (dbt-core) cannot parse this project due to package version conflicts with dbt-fusion's installed packages. The server is configured with `DBT_PATH=/Users/charlesclark/.local/bin/dbt` (the dbt-fusion binary) to avoid this.

**Tools enabled** (read-only; build/run/test excluded):
- `list` — list all models by resource type or layer
- `compile` — compile Jinja SQL without executing
- `parse` — regenerate manifest.json
- `get_lineage_dev` — model lineage from manifest
- `get_node_details_dev` — model + column details from manifest
- `search_product_docs` / `get_product_doc_pages` — dbt documentation search

**Verify** after restarting Claude Code:
```
Ask Claude: "List all models in the dbt project using the dbt MCP server"
```

---

## Snowflake MCP Server (Claude Code)

The repo includes a Snowflake MCP server so Claude Code can query Snowflake directly in-conversation. It is scoped to read-only (`SELECT`, `DESCRIBE`, `SHOW`, `USE` only).

**Setup** — the server activates automatically when Claude Code loads this project. No additional install step is needed; `uvx` pulls `snowflake-labs-mcp` on first run.

**Auth** — RSA key-pair via the existing key at `~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem` (same key used by snowsql). Connection parameters are injected via environment variables in `.mcp.json`; no plaintext credentials are stored in the file.

**Config files:**
- `.mcp.json` — server command, args, and env vars (Snowflake account, user, role, warehouse, key path)
- `snowflake_mcp_config.yaml` — service permissions (query_manager only; object_manager and semantic_manager disabled)

**Verify** after restarting Claude Code:
```
Ask Claude: "Query SELECT game_date, home_team, away_team FROM baseball_data.betting.mart_game_results LIMIT 3"
```

---

## EDA Notebooks (Marimo)

Notebooks live in [`exploratory_data_analysis/`](exploratory_data_analysis/). Each is a self-contained Marimo script with inline `uv` dependency declarations — no separate install step needed.

**Run a notebook (interactive UI):**

```bash
uv run marimo run exploratory_data_analysis/01_target_variables.py
```

Opens in the browser at `http://localhost:2718`. All cells execute reactively; the Snowflake connection is established on load using the RSA key at `~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem`.

**Edit a notebook (live-edit mode):**

```bash
uv run marimo edit exploratory_data_analysis/01_target_variables.py
```

Same URL, but cells are editable and re-run on change.

**Run headless (no browser, e.g. CI):**

```bash
uv run marimo run exploratory_data_analysis/01_target_variables.py --headless
```

**Notebooks:**

| File | Status | Key Finding |
|---|---|---|
| [`01_target_variables.py`](exploratory_data_analysis/01_target_variables.py) | Complete | Single model recommended; add `game_year`/`post_2022_rules` flag; exclude 2020; naive MAE baseline ~3.5 runs |
| [`02_feature_coverage.py`](exploratory_data_analysis/02_feature_coverage.py) | Complete | Odds cols 100% null (pre-backfill); starter platoon splits 11–17% null (debut pitchers); all other groups <5% null |
| [`03_rolling_window_stability.py`](exploratory_data_analysis/03_rolling_window_stability.py) | Complete | Season-to-date strongest for pitcher metrics; 30d ≈ STD for offense; apply `min(games_played) ≥ 15` filter |
| [`04_feature_correlations.py`](exploratory_data_analysis/04_feature_correlations.py) | Complete | Park dominates totals; pitching beats offense 2:1; top predictor: park_run_factor (r=0.122); 10 redundant pairs |
| [`05_park_and_context.py`](exploratory_data_analysis/05_park_and_context.py) | Complete | Include park + elevation; schedule features near-zero signal (r<0.023); include as binary flags only |
| [`06_bat_tracking_era.py`](exploratory_data_analysis/06_bat_tracking_era.py) | Complete | Single-model path; bat tracking max r=0.022 vs. 0.088 for park factor; OLS ΔR²<0.001; exclude Phase 4 |
| [`07_engineered_feature_lift.py`](exploratory_data_analysis/07_engineered_feature_lift.py) | Complete | 7d windows add real signal (ΔR²=0.043–0.047); handedness low-signal (ΔR²=0.001–0.002); include 7d directly |

---

## Ad-hoc Snowflake Queries (snowsql)

```bash
snowsql -c default \
  --private-key-path /path/to/rsa_key.pem \
  -q "SELECT * FROM baseball_data.betting.mart_game_results LIMIT 5;"
```

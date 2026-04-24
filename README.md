# Baseball Betting & Fantasy

ML system for predicting MLB game outcomes (total runs, run differential, win probability) using Statcast pitch data, confirmed batting lineups, starting pitcher profiles, bullpen context, and ballpark factors.

See [`project_context.md`](project_context.md) for the full architecture reference, data source documentation, model inventory, and roadmap.

---

## Current Status

**Phase 2 (Feature Store)** is complete. **Phase 3 (EDA)** is in progress — 7 notebooks complete with findings; analysis scripts for Cards 3.8 and 3.9 complete. **Phase 4 (ML Pipeline)** foundation started — data loader, CV splits, and preprocessing built.

| Domain | Status |
|---|---|
| Pitch physics and outcomes | Complete |
| Game context and results | Complete |
| Player rolling performance (batter + pitcher) | Complete |
| Team rolling offense, pitching, and splits | Complete |
| Starting pitcher game log | Complete |
| Bullpen workload and effectiveness | Complete |
| Confirmed batting lineups (staging) | Complete — 100% coverage 2015–present |
| Probable starting pitchers (staging) | Complete — 97–100% coverage for completed seasons |
| Ballpark context and run factors | Complete |
| Betting odds (staging + mart) | Events backfilled 2021–present (72–76% game coverage); odds prices partial (2023 + live 2026 only — credit gap); see data_quality/data_availability_windows.md |
| Schedule fatigue context | Complete |
| ML feature store | Phase 2 complete (2026-04-23); feature engineering complete — Cards 4.1–4.5 done (delta/momentum, handedness matchup, reliability flags, starter IP depth, era flags + game context) |
| EDA | Phase 3 in progress — notebooks 01–07 complete; Card 3.7 done (engineered feature lift); Cards 3.8 done (bullpen/starter decomposition — script); Card 3.9 done (home/away pitching asymmetry — script); Cards 3.10–3.11 queued (plan specs drafted) |
| ML pipeline foundation | Phase 4 started — `betting_ml/utils/` built: data loader, temporal CV splits, imputation + Bayesian shrinkage preprocessing (Card 4.6 complete) |
| Prediction models | Phase 4 in progress; plan specs drafted for Cards 4.7–4.12 |
| Betting application layer | Not started (Phase 6) |

---

## Repo Structure

```
├── dbt/                        # dbt-fusion project (all SQL transforms)
│   ├── models/
│   │   ├── staging/            # Type-cast and normalize raw sources (6 models)
│   │   ├── mart/               # Feature-domain mart tables (22 models)
│   │   └── feature/            # Pre-game feature assembly — Phase 2 complete (6 models)
│   └── seeds/                  # ref_teams static reference
├── scripts/                    # Python ingestion scripts
│   ├── savant_ingestion.py     # Baseball Savant (Statcast) — daily
│   ├── ingest_statsapi.py      # MLB Stats API schedule + venues
│   ├── odds_api_ingestion.py   # The Odds API events + odds
│   ├── daily_run.md            # Step-by-step daily ingestion runbook
│   └── date_utils.py           # UTC date helpers (used by odds ingestion)
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
│   │   ├── data_loader.py      # Snowflake → pandas; applies has_full_data + games_played filters
│   │   ├── cv_splits.py        # Temporal leave-one-season-out CV splits
│   │   └── preprocessing.py   # Imputation + Bayesian shrinkage pipeline
│   ├── scripts/
│   │   ├── analyze_pitching_decomp.py          # Card 3.8: bullpen vs. starter decomposition
│   │   └── analyze_home_away_pitch_asymmetry.py # Card 3.9: home/away pitching asymmetry
│   ├── evaluation/             # JSON results artifacts from analysis scripts
│   ├── models/                 # Serialized model files (Phase 4+)
│   └── tests/
│       ├── test_cv_splits.py
│       └── test_preprocessing.py
├── plan_specs/                 # Declarative PlanSpec YAML files for agentic execution
│   ├── phase_3/                # EDA analysis cards (3.8–3.11)
│   └── phase_4/                # ML pipeline cards (4.6–4.12)
├── .mcp.json                   # Snowflake MCP server config for Claude Code
├── snowflake_mcp_config.yaml   # MCP service permissions (read-only)
└── project_context.md          # Full architecture, data sources, roadmap
```

---

## Daily Ingestion

See [`scripts/daily_run.md`](scripts/daily_run.md) for the full runbook. Quick summary:

```bash
cd scripts/
uv run savant_ingestion.py batter_pitches          # Statcast — auto-detects gap
uv run ingest_statsapi.py schedule                 # Stats API — current month only
uv run odds_api_ingestion.py events                # Odds API events — 7-day window
uv run odds_api_ingestion.py odds                  # Odds API odds — h2h + totals
cd ../dbt && dbtf build                            # Refresh all mart models
```

---

## Data Sources

| Source | Coverage | Notes |
|---|---|---|
| Baseball Savant (Statcast) | 2015-04-05 – present | ~7.5M pitches; updated daily |
| MLB Stats API schedule | 2015 – present | Lineups + probable pitchers via `monthly_schedule` JSON |
| MLB Stats API venues | All active parks | Field dimensions, surface, roof, elevation |
| The Odds API | 2021 regular season – present | Events backfilled 2021–present; odds prices: 2023 partial + live 2026 (credit gap stopped full backfill) |

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

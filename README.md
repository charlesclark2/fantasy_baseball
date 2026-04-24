# Baseball Betting & Fantasy

ML system for predicting MLB game outcomes (total runs, run differential, win probability) using Statcast pitch data, confirmed batting lineups, starting pitcher profiles, bullpen context, and ballpark factors.

See [`project_context.md`](project_context.md) for the full architecture reference, data source documentation, model inventory, and roadmap.

---

## Current Status

**Phase 2 — Pre-Game Feature Assembly** is complete. The full feature store is built and validated. Phase 3 (EDA) is next.

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
| Betting odds (staging + mart) | Events backfilled 2021–present (72-76% game coverage); odds prices partial (2023 + live 2026 only — credit gap); see data_quality/data_availability_windows.md |
| Schedule fatigue context | Complete |
| ML feature store | Complete — Phase 2 done 2026-04-23; 25,146 game rows; ~23,444 training rows (2016–2025); betting odds features integrated (lowvig, live ingestion only until Card 3 backfill) |
| EDA | In progress (Phase 3) |
| Prediction models | Not started (Phase 4) |
| Betting application layer | Not started (Phase 6) |

---

## Repo Structure

```
├── dbt/                        # dbt-fusion project (all SQL transforms)
│   ├── models/
│   │   ├── staging/            # Type-cast and normalize raw sources
│   │   ├── mart/               # Feature-domain mart tables
│   │   └── feature/            # Pre-game feature assembly (Phase 2, complete)
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
├── betting_ml/                 # ML model code (Phase 4+, placeholder)
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

| File | Phase | Description |
|---|---|---|
| [`01_target_variables.py`](exploratory_data_analysis/01_target_variables.py) | Phase 3 | Target distribution analysis — total runs, run differential, home win rate (2016–2025) |

---

## Ad-hoc Snowflake Queries (snowsql)

```bash
snowsql -c default \
  --private-key-path /path/to/rsa_key.pem \
  -q "SELECT * FROM baseball_data.betting.mart_game_results LIMIT 5;"
```

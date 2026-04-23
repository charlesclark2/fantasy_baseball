# Baseball Betting & Fantasy

ML system for predicting MLB game outcomes (total runs, run differential, win probability) using Statcast pitch data, confirmed batting lineups, starting pitcher profiles, bullpen context, and ballpark factors.

See [`project_context.md`](project_context.md) for the full architecture reference, data source documentation, model inventory, and roadmap.

---

## Current Status

**Phase 1 — Data Mart** is complete. The Snowflake mart layer covers all primary feature domains needed for game outcome prediction. Phase 2 (pre-game feature assembly) is next.

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
| Betting odds (staging + mart) | Complete — forward-looking from 2026-04-23 |
| ML feature assembly | Not started (Phase 2) |
| Prediction models | Not started (Phase 4) |
| Betting application layer | Not started (Phase 6) |

---

## Repo Structure

```
├── dbt/                        # dbt-fusion project (all SQL transforms)
│   ├── models/
│   │   ├── staging/            # Type-cast and normalize raw sources
│   │   ├── mart/               # Feature-domain mart tables
│   │   └── feature/            # Pre-game feature assembly (Phase 2)
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
├── betting_ml/                 # ML model code (Phase 4+, placeholder)
├── exploratory_data_analysis/  # EDA notebooks (Phase 3+, placeholder)
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
| The Odds API | 2026-04-23 – present | Moneyline + totals; forward-looking only |

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
| EDA (planned) | Jupyter (`exploratory_data_analysis/`) |

Ad-hoc Snowflake queries:
```bash
snowsql -c default \
  --private-key-path /path/to/rsa_key.pem \
  -q "SELECT * FROM baseball_data.betting.mart_game_results LIMIT 5;"
```

# Baseball Betting & Fantasy: Project Context

## 1. Mission

Build a machine learning system capable of predicting the outcome and total runs scored in an MLB game given the pitching matchup, team matchup, and confirmed batting lineups. The system is grounded in Statcast pitch-level data and augmented with game schedule, lineup, and ballpark context from the MLB Stats API.

The project is currently in the **data mart development phase**. All modeling, feature engineering, and ML infrastructure comes after the mart layer is complete and validated.

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Data Warehouse | Snowflake |
| Transformation | dbt-fusion / `dbtf` (SQL) |
| Ingestion | Python (`scripts/savant_ingestion.py`, `scripts/ingest_statsapi.py`, `scripts/odds_api_ingestion.py`) |
| ML (planned) | Python (`betting_ml/`) |
| EDA (planned) | Jupyter (`exploratory_data_analysis/`) |

---

## 3. Canonical Join Keys

These keys govern how all models relate to one another. Using any other identifier as a join key will produce incorrect or ambiguous results.

| Grain | Key | Description |
|---|---|---|
| **Pitch** | `pitch_sk` | MD5 surrogate key derived from `game_pk + at_bat_number + pitch_number + batter_id + pitcher_id + inning + inning_half`. Uniquely identifies every pitch ever thrown. |
| **Game** | `game_pk` | MLB Stats API integer identifier for a game. Present in both Statcast and Stats API sources. All game-level models key on this. |
| **Batter** | `batter_id` | Statcast/BAM integer player ID for the batter. Used in all player-level models, splits, and rolling stats. |
| **Pitcher** | `pitcher_id` | Statcast/BAM integer player ID for the pitcher. Used in all player-level models, splits, and rolling stats. |

---

## 4. Data Sources

### 4.1 Statcast (`baseball_data.savant`)

**Ingestion:** `scripts/savant_ingestion.py` pulls pitch-level data directly from the Baseball Savant CSV export endpoint (`https://baseballsavant.mlb.com/statcast_search/csv`). Requests are chunked by single calendar day to stay under Baseball Savant's 25,000-row per-request limit. Each day is deleted before re-insertion, making reruns idempotent. The script auto-detects the last loaded date and defaults the end date to yesterday, so a daily run with no arguments keeps the table current. New Baseball Savant endpoints can be added by defining a `StatcastEndpoint` in the `ENDPOINTS` registry — no other code changes are needed.

```bash
# Daily update (auto-detects gap from last loaded date to yesterday)
uv run savant_ingestion.py batter_pitches

# Explicit range (e.g. backfill or reprocess)
uv run savant_ingestion.py batter_pitches --start-date 2026-03-20 --end-date 2026-04-21
```

**Current data:** 2015-04-05 through present (updated daily). 2026 season data begins 2026-03-25 (Opening Week).

**`batter_pitches`** — The core source table. One row per pitch per plate appearance per game. Contains 100+ columns covering:

- Game and plate appearance identifiers
- Pitch physics: release speed, spin rate, movement (pfx), release extension, arm angle
- Pitch outcome: ball, strike, swinging strike, foul, in-play
- Plate appearance result: single, double, HR, K, walk, etc.
- Batted ball tracking: exit velocity, launch angle, hit distance, batted ball type
- Expected metrics: xBA, xwOBA, xSLG (in-play events only)
- Win/run expectancy delta per pitch
- Score and base/out state at the time of each pitch
- Fielding alignment flags (shift, shade)
- **Bat tracking (2023-07-14 onward; swing events only):** `bat_speed_mph`, `swing_length_ft`, `attack_angle_degrees`, `swing_path_tilt`, `attack_direction` — Hawk-Eye bat sensor rolled out at 2023 All-Star break; ~45% population rate (swing-contact pitches only)
- **Intercept offset (2023-07-14 onward; swing events only):** `intercept_offset_x_inches`, `intercept_offset_y_inches` — same rollout and coverage as bat tracking
- **hyper_speed (2015 onward):** Available since first Statcast season; ~33% population rate (batted contact events); distinct from the 2023 Hawk-Eye bat tracking system

**`ref_players`** — Player reference table with BAM IDs, full names, and career date ranges.

### 4.2 MLB Stats API (`baseball_data.statsapi`)

**`monthly_schedule`** — One row per ingested month. The `json_field` VARIANT column contains full game metadata including confirmed pre-game batting lineups (`lineups.homePlayers`, `lineups.awayPlayers`). Ingested via `scripts/ingest_statsapi.py schedule`.

**`venues_raw`** — One row per ballpark. The `json_field` VARIANT column contains field dimensions, surface type, roof type, GPS coordinates, elevation, timezone, and cross-reference IDs. Ingested via `scripts/ingest_statsapi.py venues`.

### 4.3 The Odds API (`baseball_data.oddsapi`)

Betting market data sourced from [The Odds API](https://the-odds-api.com/). Ingested via `scripts/odds_api_ingestion.py`. All tables are append-only; raw JSON is stored at full fidelity so no source data is lost.

**`mlb_events_raw`** — One row per ingestion run of the `/v4/sports/baseball_mlb/events` endpoint. `raw_json` contains the full response array of upcoming events. Includes ingestion metadata: `load_id`, `ingestion_ts`, `x_requests_used`, `x_requests_remaining`, and the full `request_url` and `request_params` for auditability.

**`mlb_odds_raw`** — One row per event per market/region ingestion call of the `/v4/sports/baseball_mlb/odds` endpoint. `raw_json` preserves the complete event object including the nested `bookmakers → markets → outcomes` array. Convenience columns (`event_id`, `sport_key`, `home_team`, `away_team`, `bookmakers_count`) are extracted for fast filtering without JSON parsing. API credit headers (`x_requests_used`, `x_requests_remaining`) are logged and persisted with every row.

**API credit monitoring:** Every call to The Odds API returns `x-requests-used` and `x-requests-remaining` headers. These are captured by `OddsApiResponse`, logged at INFO level after each request, and written into both raw tables. If a header is missing the value is stored as `NULL` — ingestion never fails due to absent credit metadata.

**Default ingestion window:** The events endpoint defaults to a 7-day forward-looking window (today at 00:00:00 UTC through +7 days) using helpers in `scripts/date_utils.py`. The window can be overridden at the CLI.

### 4.4 Seeds

**`ref_teams`** — Static 33-row reference table (30 active franchises + legacy abbreviation entries). Contains `team_abbrev`, `team_id`, `team_name`, `league` (AL/NL), `division` (East/Central/West), and `is_active` flag.

### 4.5 Data Availability Windows

See `data_quality/data_availability_windows.md` for verified first-available dates, per-season pitch counts, and ML design implications for each feature group: Statcast full history, bat tracking (2023-07-14+), intercept offset (2023-07-14+), hyper_speed (2015+), confirmed lineups (2015+, 100% coverage), probable starters (2015+), and odds data (2026-04-23+).

---

## 5. Data Architecture

### 5.1 Feature Layer

The feature layer (`dbt/models/feature/`) is a dedicated ML boundary layer, separate from the mart layer. Models are materialized as **tables** into the `baseball_data.betting_features` Snowflake schema (distinct from `baseball_data.betting` where mart models live). All models in this layer enforce the **no-leakage rule**: every rolling window and stat lookup uses `< game_date` — no same-day data may appear in any feature.

Phase 2 (complete as of 2026-04-23) populated this layer with six pre-game feature assembly models:

| Model | Grain | Description |
|---|---|---|
| `feature_pregame_lineup_features` | Game × side | Per-team lineup feature vector with aggregated batter rolling stats and prior-season platoon splits across all 9 lineup slots |
| `feature_pregame_starter_features` | Game × starter | Per-starter feature vector with rolling pitcher stats, days rest, and prior-season platoon splits |
| `feature_pregame_team_features` | Game × team | Per-team context: rolling offense, pitching, bullpen workload and effectiveness, season record, and schedule context (days rest, streak, timezone travel) |
| `feature_pregame_park_features` | Game | Park dimensions, elevation, surface, roof type, and empirical run factors |
| `feature_pregame_odds_features` | Game | Pre-game betting market features from lowvig (selected for lowest vig across h2h and totals markets). Moneyline + totals prices, vig-adjusted implied probabilities, market vig. Leakage guard: only `ingestion_ts < commence_time` snapshots used. Prices populate going forward via live ingestion; historical prices require Card 3 backfill completion. |
| `feature_pregame_game_features` | Game | Master assembly: one wide row per game joining all five feature tables; 25,146 regular-season rows; `has_full_data` flag selects the ~23,444 data-complete training rows (2016–2025); `has_odds` standalone flag for betting market availability |

---

### 5.3 Staging Layer

Five models normalize and type-cast raw sources. All staging models are materialized as **tables** so downstream mart views have a stable, pre-computed base.

| Model | Source | Grain | Key Notes |
|---|---|---|---|
| `stg_batter_pitches` | savant.batter_pitches | Pitch | Generates `pitch_sk`; renames all columns to snake_case |
| `stg_statsapi_games` | statsapi.monthly_schedule (JSON flatten) | Game | Extracts game metadata, scores, teams, venue |
| `stg_statsapi_lineups` | monthly_schedule JSON | Player × game × side | Unpivots lineup JSON to one row per player per batting-order slot per side; deduped on month-boundary overlap |
| `stg_statsapi_lineups_wide` | stg_statsapi_lineups | Team × game × side | Wide pivot — one row per team per game with 9 batting-order slot columns |
| `stg_statsapi_venues` | statsapi.venues_raw (JSON flatten) | Venue | Extracts park dimensions, surface, roof, coordinates, elevation, timezone |
| `stg_statsapi_probable_pitchers` | monthly_schedule JSON | Game × side | Extracts `probable_pitcher_id` and name per game × side; null when rotation not yet announced; deduped to latest record per `game_pk + side` |

### 5.4 Mart Layer

Twenty-two mart models organized by grain. Pitch-grain models are materialized as **incremental tables** (merge on `pitch_sk`). Aggregate and rolling models are materialized as **tables**.

#### Pitch-Grain Models (7 models)
All share `pitch_sk` as the primary key. They can be joined to one another without duplication.

| Model | Contents |
|---|---|
| `mart_pitch_game_context` | Count state, base state, outs, score differential, win/run expectancy, count leverage bucket |
| `mart_pitch_pitcher_profile` | Pitcher identity, handedness, age, days rest, times through the order |
| `mart_pitch_hitter_profile` | Batter identity, handedness, age, prior PAs in this game |
| `mart_pitch_characteristics` | Release speed, spin rate, pfx movement, release extension, zone, pitch type/name |
| `mart_pitch_play_event` | Pitch description, plate appearance event, batter/pitcher outcome flags |
| `mart_pitch_hit_characteristics` | Exit velocity, launch angle, hit distance, batted ball type, contact quality flags (`is_barrel`, `is_hard_hit`, `is_sweet_spot`), xBA/xwOBA, bat tracking (2023+) |
| `mart_pitch_fielding` | Infield/outfield alignment classification, fielder IDs by position, shift/shade flags |

#### Game-Level Models (2 models)

| Model | Contents |
|---|---|
| `mart_game_results` | Final score, teams, league/division, winner, run differential, extra innings flag, interleague flag, `venue_id`, `venue_name` |
| `mart_park_run_factors` | Empirical run environment per ballpark: `runs_per_game_at_park` (season average) and `park_run_factor_3yr` (3-year rolling avg). One row per `venue_id` per `game_year`. Regular season only; minimum 10 games. Join to `stg_statsapi_venues` on `venue_id` for physical park dimensions. |

#### Player Rolling Stats (2 models)
One row per player per game. Rolling windows: 7/14/30-day + season-to-date. Regular season only (`game_type = 'R'`).

| Model | Contents |
|---|---|
| `mart_batter_rolling_stats` | Batting average, wOBA, xwOBA, K%, BB%, whiff rate, barrel rate, chase rate, contact rate, hard-hit % |
| `mart_pitcher_rolling_stats` | K%, BB%, whiff rate, barrel rate allowed, hard-hit % allowed, xwOBA against, fastball velocity trend |

#### Team Rolling Stats (4 models)
One row per team per game. Rolling windows: 7/14/30-day + season-to-date. Regular season only.

| Model | Contents |
|---|---|
| `mart_team_rolling_offense` | Runs scored, wOBA, xwOBA, K%, BB%, SLG, hard-hit %, barrel rate |
| `mart_team_rolling_pitching` | Runs allowed, wOBA against, xwOBA against, K%, BB% |
| `mart_team_vs_pitcher_hand` | Offensive splits vs. RHP and LHP starters: runs, wOBA, xwOBA, K%, BB%, hard-hit %, barrel rate |
| `mart_home_away_splits` | Offense and pitching split by home/away context: runs, wOBA, xwOBA, K%, BB%, SLG, hard-hit %, barrel rate — for each side separately |

#### Specialty Models (7 models)

| Model | Grain | Contents |
|---|---|---|
| `mart_team_season_record` | Team × game | Cumulative W/L record and win % through each date |
| `mart_starting_pitcher_game_log` | Starter × game | IP, outs recorded, K, BB, earned runs, ERA, avg fastball velo per start |
| `mart_bullpen_workload` | Team × game | Bullpen fatigue: pitches thrown, relievers used, closer/high-leverage appearances over 1/3/7-day windows |
| `mart_bullpen_effectiveness` | Team × game | Bullpen quality: K%, BB%, xwOBA against, hard-hit %, whiff rate, IP over 14- and 30-day rolling windows. Complement to `mart_bullpen_workload`; join on `team_abbrev + game_pk` |
| `mart_team_schedule_context` | Team × game | Schedule fatigue context: days rest (null on Opening Day), games_last_7d, games_last_14d, home/away streak length, timezone travel signal. Join on `team_abbrev + game_pk`. |
| `mart_batter_vs_handedness_splits` | Batter × pitcher hand × season | AVG, wOBA, xwOBA, K%, BB%, hard-hit % vs. LHP and RHP |
| `mart_pitcher_vs_handedness_splits` | Pitcher × batter hand × season | K%, BB%, wOBA against, hard-hit % against vs. LHB and RHB |
| `mart_head_to_head_team_history` | Team pair × season | Season and all-time H2H record, run differential, and extra-innings rate for every franchise pair; abbreviations normalized to canonical form (e.g. OAK → ATH) for continuous franchise history |

#### Odds API Models (2 models)

| Model | Grain | Contents |
|---|---|---|
| `mart_odds_events` | Event | One row per event_id (latest ingestion snapshot); authoritative event dimension with commence_time, home_team, away_team. Join key for mart_odds_outcomes. |
| `mart_odds_outcomes` | Ingestion snapshot × event × bookmaker × market × outcome | Full history of bookmaker odds. Preserves all ingestion snapshots to support line movement analysis and cross-bookmaker comparisons. Includes derived flags: `is_totals_market`, `is_home_outcome`, `is_away_outcome`. |

#### Bridge Models (1 model)

| Model | Grain | Contents |
|---|---|---|
| `mart_game_odds_bridge` | Game (`game_pk`) | One row per game in mart_game_results, left-joined to mart_odds_events on game_date + full team names (normalized to Stats API canonical names). `event_id` is null for games without odds coverage (pre-2021 or games not returned by The Odds API). `has_odds` boolean flag for quick filtering. Match rates: 72–78% for 2021–2026 regular season games (Odds API covers ~10 of ~13 games per day). Team name normalization: "Cleveland Indians" → "Cleveland Guardians" (2021), "Oakland Athletics" → "Athletics" (2021–2025). |

---

## 6. Key Design Notes

**No-leakage rule (feature layer):** Every rolling window lookup and stat join in `dbt/models/feature/` must use data strictly from before the game date. The enforced patterns are:
- Rolling window joins: `stats.game_date::date < game_date` (strictly less than — never `<=`)
- Platoon splits: `game_year = year(game_date) - 1` (prior season only — full-season in-progress aggregates would leak)
- Park run factors: `prf.game_year = game_year - 1` (prior season only)
- Season record: `record_date = game_date - 1` (standings as of the day before)

Violations allow the model to "see" same-day game results during training, producing optimistic in-sample metrics that collapse out-of-sample. The full code review checklist and a Snowflake spot-check against game_pk 777235 (LAD vs HOU, 2025-07-04) are documented in `data_quality/leakage_audit.md`. All five feature models passed the audit on 2026-04-23.

**Bat tracking availability:** `bat_speed`, `swing_length`, `attack_angle`, `attack_direction`, and `swing_path_tilt` are available **starting 2023-07-14** (Hawk-Eye bat sensor; mid-season All-Star break rollout). They populate for swing-contact events only (~45% of pitches in 2024+; ~20% for the 2023 partial season). ML features built on these columns must treat them as an optional era-specific block — models trained on 2015–present data must have a fallback path that omits them.

**hyper_speed availability:** `hyper_speed` has been available **since 2015-04-05** and is distinct from the 2023 bat tracking system. It populates for batted contact events (~33% of pitches) and is usable for the full training history.

**Expected metrics availability:** `xba`, `xwoba`, `xslg` are only populated for in-play events (balls put in play). They are null for called strikes, swinging strikes, fouls, and walks.

**Intercept offset fields** (`intercept_offset_x_inches`, `intercept_offset_y_inches`) are available **starting 2023-07-14** — same rollout date as bat tracking, not 2024. Swing-contact events only, same ~45% population rate.

**Rolling window season isolation:** All rolling window CTEs partition by `game_year` to prevent November stats from bleeding into April of the following season.

**Regular season filter:** All rolling stats, splits, and workload models apply `game_type = 'R'` to exclude Spring Training, All-Star, Wild Card, Division Series, Championship Series, and World Series games. The prediction target is regular season games.

**Incremental merge on `pitch_sk`:** Pitch-grain mart models use `MERGE` so late-arriving Statcast corrections are applied rather than duplicated.

---

## 7. Known Data Quality Issues

### Data Quality Workflow

Data quality issues are tracked in two files under `data_quality/`:

- **`data_quality/open_data_quality_issues.md`** — All unresolved issues. Each entry carries a root-cause description, a diagnostic SQL query (where available), a proposed resolution, and a TBD resolution date.
- **`data_quality/resolved_data_quality_issues_april_2026.md`** (and future month files) — Issues that have been fully investigated, remediated in the schema or source, and closed out with a resolution date.

**Resolution process:**
1. Identify the failing test and its severity (`error` blocks the build; `warn` passes but flags)
2. Run the diagnostic query against `baseball_data.betting.*` via snowsql to characterize the failing rows (counts, distributions, game/player context)
3. Determine root cause: bad source data, overly tight test bounds, model logic bug, or test design issue
4. Apply the appropriate fix: relax bounds with `warn_if`/`error_if` thresholds, correct the source row, fix the model SQL, or remove/replace the test
5. Move the issue from `open_data_quality_issues.md` to the current month's resolved file, with full findings and the diagnostic query

### Resolved
| Issue | Resolution |
|---|---|
| 25 pitches with `balls = 4` | Accepted; `error_if >= 26` threshold set |
| 1 pitch with `strikes = 3` on a hit | Fixed in source |
| 413 pitches with `release_speed < 40 mph` (Eephus) | Bounds relaxed to 28–110 mph |
| 748 pitches with `effective_speed < 40 mph`, 1 at 194.6 mph | Bounds relaxed to 26–115 mph |
| `release_extension_ft` outside 0–9 ft (381 rows: 361 near-boundary noise, 19 extreme outliers, 1 negative) | Bounds relaxed to -0.5–10.0 ft; `error_if >= 25` threshold set |
| `innings_pitched` float division bug in `mart_starting_pitcher_game_log` | Fixed: `floor(outs/3) + (mod(outs,3) * 0.1)` |
| Duplicate lineups from month-boundary API overlap | Fixed: `QUALIFY ROW_NUMBER() = 1` in `stg_statsapi_lineups` |
| Raw count columns (`strikeouts`, `walks`, `at_bats`, `total_bases`, `hard_hit_balls`, `barrels`, `batted_balls`) dropped from final SELECT in `mart_team_vs_pitcher_hand` | Added missing columns to `rolling` CTE SELECT list |
| Null `is_barrel`, `is_hard_hit`, `is_sweet_spot`, `is_hard_hit_sweet_spot` in `mart_pitch_hit_characteristics` | Fixed: `coalesce(..., false)` on all four boolean casts; sac bunts and early Statcast coverage gaps produce null source fields |
| Null fielding alignment flags (9 derived flags) in `mart_pitch_fielding` | Fixed: `coalesce(..., false)` on all nine boolean casts; 70,778 regular-season pitches across all years lack Statcast alignment tracking |
| `hard_hit_pct > 1` and `hard_hits > batted_balls` in `mart_batter_vs_handedness_splits` | Fixed: added `field_error` to `is_batted_ball` event list; field errors are batted balls with exit velocity but were missing from the case expression |
| Duplicate `game_pk` values in `stg_statsapi_games` (529 extra rows from postponed/rescheduled games) | Fixed: `QUALIFY ROW_NUMBER() = 1` dedup keeping the scored Final row over Postponed; Cancelled kept over Postponed when no Final exists |
| Null `woba` and rolling `woba_*` in `mart_team_vs_pitcher_hand` (5 tests) | Test expressions relaxed to `is null or (col >= 0)`; null valid when woba_denom=0; early Statcast source has null woba_denom for batted balls, causing woba > 2 for 3 games |
| Null `hard_hit_balls` and `barrels` in `mart_team_vs_pitcher_hand` for games with no balls in play (2 tests) | Fixed: `coalesce(sum(is_hard_hit::integer), 0)` and `coalesce(sum(is_barrel::integer), 0)` in `game_offense` CTE |
| Null `woba` and `woba_against` in `mart_home_away_splits` (2 tests) | Test expressions relaxed to `is null or (col >= 0)`; same Statcast woba_denom source issue as `mart_team_vs_pitcher_hand` |
| `games_std >= games_7d` test fails at season boundaries in `mart_home_away_splits` (1 test) | Test removed; `games_7d` window has no year partition and can span season boundaries while `games_std` resets — test design flaw, not a data error |
| Null `ingestion_ts` in `baseball_data.oddsapi.mlb_odds_raw` (source test) | Self-resolved: null rows eliminated when table was rebuilt in commit 3786845; current ingestion script always populates `ingestion_ts`; 64/64 oddsapi chain tests pass |

---

## 8. Current State Assessment

The project has a well-structured, well-documented data mart that covers the primary feature domains needed for game outcome prediction:

| Domain | Status |
|---|---|
| Pitch physics and outcomes | Complete |
| Game context and state | Complete |
| Batter and pitcher identity | Complete |
| Game results | Complete |
| Player rolling performance | Complete |
| Team rolling offense and pitching | Complete |
| Home/away context splits | Complete |
| Platoon splits (team, batter, pitcher) | Complete |
| Head-to-head franchise history | Complete |
| Starting pitcher game log | Complete |
| Bullpen workload | Complete |
| Bullpen effectiveness (quality) | Complete — `mart_bullpen_effectiveness` with 14/30-day K%, BB%, xwOBA against, hard-hit %, whiff rate, IP |
| Schedule fatigue context | Complete — `mart_team_schedule_context` with days rest, games_last_7d/14d, home/away streak, timezone travel signal |
| Lineup data (confirmed pre-game) | Complete (staging) |
| Ballpark context | Complete — physical dimensions in staging (`stg_statsapi_venues`); empirical run factors in `mart_park_run_factors`; `venue_id` joined to `mart_game_results` |
| Data quality tests | Mostly complete; 2 open items (intentional warns, irresolvable Statcast source gap) |
| ML feature store | Complete — Phase 2 done 2026-04-23; six feature models built, tested, and validated; 25,146 regular-season game rows; `has_full_data` training subset ~23,444 games (2016–2025 complete seasons); `has_odds` flag available for betting market features (prices populate going forward via live ingestion; historical coverage requires Card 3 backfill) |
| Prediction models | Not started |
| Betting/sizing layer | Not started |

The main gap between current state and a deployable prediction model is the **feature assembly layer** — joining the mart tables into a single pre-game feature vector per game — and the **ML pipeline** itself.

---

## 9. Roadmap

### Phase 1 — Complete and Stabilize the Data Mart (Current Phase)

Estimated completion: before ML work begins.

**Goals:**
- ~~Resolve all pending data quality issues~~ ✓ Complete — all `error`-severity tests pass; 2 remaining items are intentional `warn`-severity tests for `mart_pitch_fielding` (irresolvable Statcast sensor gaps, acknowledged limitations)
- ~~Confirm `mart_pitch_hit_characteristics` null flag root cause and fix~~ ✓ Complete — `coalesce(..., false)` applied to all four boolean casts; sac bunts and early Statcast coverage gaps documented
- ~~Confirm `mart_pitch_fielding` null flag root cause and fix~~ ✓ Complete — `coalesce(..., false)` applied to all nine alignment boolean flags; 70,778-row sensor gap in source acknowledged as irresolvable
- ~~Add `venue_id` / park factor join to `mart_game_results`~~ ✓ Complete — `venue_id` and `venue_name` joined from `stg_statsapi_games`; `mart_park_run_factors` built with season and 3-year rolling run factors per venue; all tests pass
- ~~Confirm lineup data is reliably populated for historical games (coverage audit)~~ ✓ Complete — 100% coverage 2015–2026; lineup features are a required join with no date cutoff
- ~~Document data availability windows (Statcast coverage by year, lineup coverage by year)~~ ✓ Complete — verified against actual Snowflake row counts; intercept offset corrected to 2023-07-14 (not 2024); full table in `data_quality/data_availability_windows.md`

**Deliverables:**
- ✓ All dbt tests passing at error thresholds (2 intentional `warn`-severity tests remain — by design)
- ✓ Coverage audit documented in `data_quality/open_data_quality_issues.md`
- ✓ Data availability windows documented in `data_quality/data_availability_windows.md`

---

### Phase 1 Enhancement — Historical Odds Backfill

The current odds pipeline is forward-looking only (live ingestion started 2026-04-23). To make odds features usable for model training and backtesting, historical events and odds must be backfilled for the 2021–2025 regular seasons using The Odds API historical endpoints. These four cards extend Phase 1 and must be completed before Phase 3 EDA or Phase 4 model training can incorporate betting market features.

---

#### Card 1 — Ingest Historical MLB Events from The Odds API (2021–present)

**Title:** Ingest historical MLB events from The Odds API — 2021 to present

**Description:**

*Technical implementation:* Add a `historical-events` subcommand to `scripts/odds_api_ingestion.py`. The endpoint is `GET /v4/historical/sports/baseball_mlb/events` with a `date` parameter in ISO 8601 UTC format. For each game date from the 2021 season opener through 2026-04-22 (the day before live ingestion began):

1. Determine the first game start time on that date (query `baseball_data.betting.mart_game_results` for `MIN(game_datetime_utc)` where `game_date = <date>` and `game_type = 'R'`)
2. Set the `date` parameter to 1 hour before the first game start on that date (e.g., if first game is 13:05 ET / 17:05 UTC, use `16:05:00Z`)
3. Pass `commenceTimeFrom` and `commenceTimeTo` scoped to that calendar date (UTC) to limit the response to that day's games
4. Write each response into `baseball_data.oddsapi.mlb_events_raw` — same table as live events — tagged with `source_endpoint = '/v4/historical/sports/baseball_mlb/events'` for auditability

The subcommand must accept `--start-date` and `--end-date` CLI args to support incremental backfills and reruns. The script should skip dates with no regular season games (query `mart_game_results` to build the game-date list). Respect API rate limiting with the existing `REQUEST_DELAY` between calls.

*Blockers:* None — fully independent. Note: ~810 game days across 2021–2025 regular seasons = ~810 API requests. Verify available credits before running the full backfill.

**Acceptance criteria:**
- [ ] New `historical-events` subcommand added to `odds_api_ingestion.py` with `--start-date` and `--end-date` args
- [ ] Script queries `mart_game_results` to build the list of game dates in range; skips non-game dates
- [ ] Each API call uses `date` = 1 hour before the earliest game start UTC on that date
- [ ] All responses inserted into `baseball_data.oddsapi.mlb_events_raw` with correct ingestion metadata columns populated
- [ ] API credits logged after each call
- [ ] Full backfill for 2021–2025 regular seasons completes with no unhandled errors
- [ ] `event_id` is non-null for all returned event rows

---

#### Card 2 — Add Decimal Odds Column to Staging and Mart Models

**Title:** Add `outcome_price_decimal` derived column to stg_oddsapi_odds and mart_odds_outcomes

**Description:**

*Technical implementation:* American odds → decimal odds conversion:
- Positive American odds (≥ 100): `decimal_odds = (outcome_price_american / 100.0) + 1`
- Negative American odds (< 0): `decimal_odds = (100.0 / ABS(outcome_price_american)) + 1`

Add `outcome_price_decimal FLOAT` as a derived column in two dbt models:

1. `dbt/models/staging/stg_oddsapi_odds.sql` — add the computed column immediately after `outcome_price_american` in the final SELECT using a `CASE WHEN outcome_price_american >= 100 THEN ... ELSE ... END` expression
2. `dbt/models/mart/mart_odds_outcomes.sql` — pass `outcome_price_decimal` through from staging (no re-derivation needed)

Update `schema.yml` for both models with a column description and a `not_null` test scoped to rows where `outcome_price_american is not null`.

*Blockers:* None — fully independent of Cards 1, 3, and 4.

**Acceptance criteria:**
- [ ] `outcome_price_decimal` column added to `stg_oddsapi_odds` with correct formula for positive and negative American odds
- [ ] `outcome_price_decimal` column added to `mart_odds_outcomes` (passed through from staging)
- [ ] Spot-check passes: +150 → 2.50, −110 → 1.909 (rounded), +100 → 2.00, −200 → 1.50
- [ ] Column is non-null for all rows where `outcome_price_american` is non-null
- [ ] `schema.yml` updated with column description for both models
- [ ] `dbtf build --select stg_oddsapi_odds mart_odds_outcomes` passes all tests

---

#### Card 3 — Ingest Historical Odds Using Event IDs (blocked by Card 1)

**Title:** Ingest historical MLB odds from The Odds API using event IDs from historical events backfill — 2021 to present

**Description:**

*Technical implementation:* Add a `historical-odds` subcommand to `scripts/odds_api_ingestion.py`. This command reads distinct event IDs from `baseball_data.oddsapi.mlb_events_raw` (populated by Card 1) for a given date range, then for each event fetches historical odds by calling:

`GET /v4/historical/sports/baseball_mlb/events?apiKey=...&date=<snapshot_date>&eventIds=<event_id>&markets=h2h,totals&regions=us,us2`

Where `snapshot_date` = the event's `commence_time` minus 1 day (ISO 8601 UTC). This returns the odds snapshot from one day before the game — the pre-game market line.

Results are written to `baseball_data.oddsapi.mlb_odds_raw` — the same target as live odds ingestion — so `stg_oddsapi_odds`, `mart_odds_outcomes`, and all downstream models consume them automatically without schema changes.

The subcommand must accept `--start-date` / `--end-date` args to allow incremental backfills. Both `h2h` and `totals` markets must be fetched per event (two calls per event). Apply `REQUEST_DELAY` between calls.

*Blockers:* **Blocked by Card 1.** Event IDs must be present in `mlb_events_raw` before historical odds can be fetched. Estimated API credit consumption: ~810 game days × ~15 events/day × 2 markets = ~24,300 requests. Confirm credits are available before running the full backfill.

**Acceptance criteria:**
- [ ] New `historical-odds` subcommand added to `odds_api_ingestion.py` with `--start-date` and `--end-date` args
- [ ] Script queries `baseball_data.oddsapi.mlb_events_raw` to get distinct event IDs and their `commence_time` for the target date range
- [ ] For each event, `date` parameter = `commence_time` minus 1 day (ISO 8601 UTC)
- [ ] Both `h2h` and `totals` markets fetched per event
- [ ] Results written to `baseball_data.oddsapi.mlb_odds_raw` with all required metadata columns populated
- [ ] Rate limiting applied between all API calls
- [ ] `--start-date` / `--end-date` filtering works correctly for incremental reruns
- [ ] Full 2021–2025 backfill completes with no unhandled errors

---

#### Card 4 — Verify Historical Odds Flow Through Staging, Mart, and Bridge Models (blocked by Cards 1 and 3)

**Title:** Verify historical odds data flows correctly through all downstream dbt models and update coverage documentation

**Description:**

*Technical implementation:* After Cards 1 and 3 populate `mlb_events_raw` and `mlb_odds_raw` with historical data, verify that all downstream dbt models handle the expanded dataset correctly and that no existing tests break:

1. `stg_oddsapi_events` — confirm lateral flatten + dedup logic correctly handles events with `commence_time` in the past; no grain violations expected
2. `stg_oddsapi_odds` — confirm no null `outcome_price_american` or grain duplicates introduced by historical rows
3. `mart_odds_events` — dedup-to-latest logic must still return one row per `event_id`; verify historical events appear with correct `commence_time` and `commence_date`
4. `mart_odds_outcomes` — verify `is_totals_market`, `is_home_outcome`, `is_away_outcome` flags are correct on historical rows; `outcome_price_decimal` (from Card 2) must be populated
5. `mart_game_odds_bridge` — currently joins `mart_game_results` to `mart_odds_events` on `game_date + full team names`; with historical odds present, match rate for 2021–2025 games should improve significantly. Verify join logic handles past games correctly and document the resulting per-season match rate.

Update `data_quality/data_availability_windows.md` to reflect the expanded odds coverage window (2021 regular season onward).

*Blockers:* **Blocked by Cards 1 and 3.** Historical raw data must be present in both source tables before downstream verification is meaningful. Card 2 (decimal odds) should also be merged before running this verification so the full column set is tested together.

**Acceptance criteria (completed 2026-04-23):**
- [x] `dbtf build` passes all tests after historical backfill with no new failures (962 pass / 18 warn / 0 error)
- [x] Row count in `stg_oddsapi_events` reflects all historical + live events with no duplicates per `event_id` (9,419 distinct event_ids = 9,419 total rows)
- [x] Row count in `stg_oddsapi_odds` reflects all historical + live odds rows with no grain violations (0 null prices, 0 grain duplicates)
- [x] `mart_game_odds_bridge.has_odds = true` for 2021–2025 regular season games where odds were available (72.4–75.9% per season after team name normalization fix)
- [x] No unexpected nulls in `outcome_price_decimal` for historical rows in `mart_odds_outcomes`
- [x] Per-season match rate in `mart_game_odds_bridge` documented in `data_quality/open_data_quality_issues.md` with pre-fix vs post-fix table
- [x] `data_quality/data_availability_windows.md` updated with full odds coverage section including per-season match rates

---

### Phase 2 — Pre-Game Feature Assembly ✓ Complete (2026-04-23)

The prediction task requires a single feature vector per game, assembled from information available **before first pitch**. All five feature models are built, tested, and validated.

**Models built (all in `dbt/models/feature/`, schema: `baseball_data.betting_features`):**

| Model | Grain | Description |
|---|---|---|
| `feature_pregame_lineup_features` | Game × side | Aggregated batter rolling stats (30-day + season-to-date) and prior-season platoon splits across all 9 lineup slots |
| `feature_pregame_starter_features` | Game × starter | Rolling pitcher stats (K%, xwOBA against), days rest, and prior-season platoon splits; source is `stg_statsapi_probable_pitchers` |
| `feature_pregame_team_features` | Game × team | Rolling offense, rolling pitching, platoon splits vs. L/R, season record, bullpen workload, bullpen effectiveness, and schedule context (days rest, games_last_7d/14d, home/away streak, timezone travel) |
| `feature_pregame_park_features` | Game | Park dimensions, elevation, surface, roof type (from `stg_statsapi_venues`), and prior-season empirical run factors (from `mart_park_run_factors`) |
| `feature_pregame_odds_features` | Game | Pre-game betting market signals from lowvig: moneyline (h2h) and totals prices, vig-adjusted implied probabilities, market vig. Bookmaker selected 2026-04-23: lowvig has lowest median vig in both h2h (2.33%) and totals (3.39%) markets with ≥99% event coverage. Leakage guard enforced: only `ingestion_ts < commence_time` snapshots used. Prices populate going forward (live daily ingestion); historical prices require Card 3 backfill. |
| `feature_pregame_game_features` | Game | Master assembly: one wide row per game joining all five feature tables; 25,146 regular-season rows; `has_odds` standalone flag |

**Training set (has_full_data = true) by season — verified 2026-04-23:**

| Season | Games |
|---|---|
| 2015 | 0 (no prior-season run factor) |
| 2016–2019 | ~9,268 |
| 2020 | 801 (COVID 60-game season) |
| 2021–2025 | ~11,665 |
| **Total (2016–2025 complete)** | **~23,444** |

**Key design constraints enforced:**
- All features use data strictly before game_date: rolling stats `< game_date`, platoon splits `game_year - 1`, park factors `game_year - 1`, season record `game_date - 1`
- `has_full_data` flag selects the data-complete training subset (both lineups confirmed, both starters have prior history, park has prior-season run factor)
- Full leakage audit documented in `data_quality/leakage_audit.md`; spot-check against game_pk 777235 (LAD vs HOU, 2025-07-04) passed

**Lineup coverage audit (completed 2026-04-23):**

`stg_statsapi_lineups_wide` has **100% coverage for every regular season from 2015 through 2026** — lineup features are a required join with no date cutoff needed.

---

### Phase 3 — Exploratory Data Analysis

Before fitting models, spend time in `exploratory_data_analysis/` to:

- Validate that assembled features are plausibly correlated with game outcomes
- Identify the most predictive feature groups (team rolling offense, pitcher wOBA allowed, park factors, lineup quality)
- Assess the predictive signal of bat tracking features (2023+ only) vs. traditional metrics (full history)
- Investigate target variable distribution: total runs scored, run differential, and binary win outcome
- Identify training set boundaries: minimum data needed per team/player before a feature is reliable
- Check for multicollinearity (wOBA vs. xwOBA vs. AVG; pitcher K% vs. whiff rate)

**Key questions to answer:**
1. How many games of rolling history are needed before batter/pitcher stats stabilize?
2. Is lineup slot order predictive (cleanup hitter vs. 9th spot) or should lineups be aggregated?
3. Do park factors materially improve predictions beyond team rolling offense?
4. Is the 2023+ bat tracking data worth building a separate model era?

---

### Phase 4 — Baseline Prediction Models

Build initial models in `betting_ml/` using the assembled feature store from Phase 2.

**Targets:**
- **Total runs scored** (regression; enables over/under analysis)
- **Run differential** (regression; calibrated to win probability)
- **Binary win outcome** (classification; moneyline proxy)

**Baseline approach:**
1. XGBoost regression and classification baselines — strong performance on tabular data, handles missing values (pre-2023 bat tracking nulls), interpretable via SHAP
2. Train on regular season games with confirmed lineups (limit to `game_type = 'R'` where lineup data is populated)
3. Cross-validate by season (train on years N−k through N−1, evaluate on year N) to respect temporal ordering
4. Evaluate regression targets with MAE and RMSE; classification with log loss and Brier score
5. Calibrate probability outputs (Platt scaling or isotonic regression) before any EV calculations

**Feature groups to evaluate:**
- Team rolling offense (7/14/30-day wOBA, runs, K%, BB%)
- Team rolling pitching (7/14/30-day wOBA against, K%, BB%)
- Platoon adjustment (team offense vs. pitcher hand)
- Starter features (recent ERA, xwOBA against, K%, fastball velo trend)
- Lineup features (aggregated batter wOBA + handedness composition vs. starter)
- Park features (dimensions, elevation, surface)
- Season record (win% as proxy for overall team quality)

---

### Phase 5 — Model Refinement and Feature Expansion

Once baselines are established:

**Feature additions:**
- Weather data (temperature, wind speed/direction, humidity) — strong park-era interaction; requires external data source
- Umpire tendencies (ball/strike zone size) — significant but requires additional data
- Bullpen availability score: derive from `mart_bullpen_workload` (days rest + recent IP for top relievers)
- Travel schedule / home vs. away streaks
- Batter/pitcher head-to-head history (build from `stg_batter_pitches` with `GROUP BY batter_id, pitcher_id`)
- Player injury status (requires external data source)

**Model improvements:**
- Neural network approaches (TabNet, MLP) if tabular baselines plateau
- Ensemble / stacking of run total and win probability models
- Separate era models: pre-2023 (no bat tracking) and 2023+ (full bat tracking features)
- Position-aware lineup encoding (slot 1–9 weighted differently, or positional encoding)

**Validation improvements:**
- Walk-forward evaluation by week, not just season
- Calibration curves by run total bucket (high-scoring vs. pitcher-duel games)
- Separate evaluation for home vs. away, dome vs. outdoor, AL vs. NL

---

### Phase 6 — Betting Application Layer

Build the `betting_ml/` application layer that translates model outputs into actionable information.

**Components:**

| Component | Description |
|---|---|
| Pre-game prediction pipeline | Given tomorrow's confirmed lineups and starting pitchers, produce predicted run total, run differential, and win probability for each game |
| Market comparison | Compare model probability to implied probability from current market odds (requires odds data source) |
| Expected value calculator | `EV = (model_probability × payout) - (1 - model_probability)` |
| Kelly criterion sizer | `f* = (bp - q) / b` where `b` = decimal odds - 1, `p` = model win prob, `q` = 1 - p; apply fractional Kelly for risk management |
| Backtesting framework | Simulate historical betting decisions using model outputs vs. closing line odds to estimate long-run edge |
| Daily pipeline | Automated pre-game scoring: fetch that day's confirmed lineups via Stats API, run prediction, output edge rankings |

**Risk controls:**
- Never bet on games with missing lineup data (model degrades significantly)
- Minimum confidence threshold before flagging a game as actionable
- Track closing line value (CLV): if the model identified edge that the market later confirmed, the model is functioning correctly

---

### Phase 7 — Production Infrastructure

Operationalize the full stack:

- Scheduled dbt runs (daily) to refresh staging and mart tables with new Statcast data
- Scheduled ingestion of that day's lineup data via `ingest_statsapi.py`
- Automated model scoring pipeline that triggers once lineups are confirmed (typically 3–4 hours before first pitch)
- Output dashboard or notification system for actionable game flags
- Model performance monitoring: track prediction accuracy week-over-week, flag model drift

---

## 10. Predicted Timeline

| Phase | Milestone | Estimated State |
|---|---|---|
| Phase 1 | All dbt tests passing, data quality issues resolved | Near-term (days to weeks) |
| Phase 2 | Pre-game feature assembly mart models built and tested | Weeks |
| Phase 3 | EDA complete, target variable and feature candidates validated | Weeks |
| Phase 4 | Baseline XGBoost models trained, cross-validated, calibrated | Weeks to months |
| Phase 5 | Refined models with expanded feature set, era-aware approach | Months |
| Phase 6 | Betting application layer with EV calculation and backtesting | Months |
| Phase 7 | Automated daily pipeline, monitoring, dashboard | Months |

---

## 11. File Reference

| Path | Purpose |
|---|---|
| `dbt/dbt_project.yml` | dbt project configuration (profile, materializations) |
| `dbt/models/sources.yml` | Source table definitions (savant, statsapi) |
| `dbt/models/staging/schema.yml` | Staging model schemas and tests |
| `dbt/models/mart/schema.yml` | Mart model schemas and tests |
| `dbt/models/feature/schema.yml` | Feature layer model schemas and tests; materializes into `baseball_data.betting_features` |
| `dbt/seeds/ref_teams.csv` | Static team reference (30 franchises + legacy abbreviations) |
| `dbt/README.md` | dbt layer documentation |
| `data_quality/open_data_quality_issues.md` | Open data quality issues — pending investigation and resolution |
| `data_quality/resolved_data_quality_issues_april_2026.md` | Resolved data quality issues — April 2026 |
| `data_quality/data_availability_windows.md` | Verified first-available dates and per-season coverage for all feature groups; Phase 3 EDA and era-aware model scoping reference |
| `scripts/daily_run.md` | **Daily ingestion runbook** — step-by-step commands to keep all Snowflake source tables current; covers savant, statsapi, and odds_api ingestion plus dbt refresh |
| `scripts/savant_ingestion.py` | Baseball Savant CSV ingestion; chunked by day, idempotent, extensible via `StatcastEndpoint` registry; subcommands: `batter_pitches` |
| `scripts/ingest_statsapi.py` | Python ingestion for Stats API schedule and venues; schedule subcommand defaults to current month only to avoid full historical re-processing |
| `scripts/odds_api_ingestion.py` | Python ingestion for The Odds API events and odds endpoints; two subcommands: `events` and `odds` |
| `scripts/date_utils.py` | Reusable UTC date/time helpers (`format_iso_utc`, `default_window`) used by odds ingestion; injectable `now` parameter makes functions unit-testable |
| `scripts/tests/test_date_utils.py` | Pytest unit tests for `date_utils` (19 tests covering format, window boundaries, timezone conversion, rollover) |
| `scripts/ddl/oddsapi_raw_tables.sql` | DDL for `baseball_data.oddsapi.mlb_events_raw` and `mlb_odds_raw`; run once via snowsql to create tables |
| `betting_ml/` | Placeholder — ML model code lives here (Phase 4+) |
| `exploratory_data_analysis/` | Placeholder — EDA notebooks live here (Phase 3+) |

---

## 12. Project Management

### Trello Card Format

Every Trello card must include:

**Title** — Action-oriented, specific enough to understand scope without opening the card.

**Description** — Three sections, kept concise:

*Technical implementation* — Bullet points covering: what to build, which source tables it depends on, grain, key logic or design decisions, and any architectural constraints (e.g., no-leakage rule). Avoid exhaustive column lists — reference table names and let the implementer read the schema.

*Blockers* — Prerequisite cards, missing data, or open decisions that must be resolved before this card can start.

*Acceptance criteria* — Short, checkable conditions. Each criterion must be verifiable (e.g., "`dbtf build --select <model>` passes all tests", "row count matches expected grain"). Avoid vague criteria ("looks good", "seems correct"). Aim for 5–8 criteria per card.

**Example of correct scope and style:** See the Card 4 (Verify historical odds flow) text in Section 9 — Phase 1 Enhancement. That card is the reference for length and detail level.

---

## 13. Tooling Reference

### Daily ingestion runbook

See `scripts/daily_run.md` for the full step-by-step daily run sequence. Quick summary:

```bash
cd scripts/
uv run savant_ingestion.py batter_pitches          # Statcast — auto-detects gap
uv run ingest_statsapi.py schedule                 # Stats API — current month only
uv run odds_api_ingestion.py events                # Odds API events — 7-day window
uv run odds_api_ingestion.py odds                  # Odds API odds — h2h + totals
cd ../dbt && dbtf build                            # Refresh all mart models
```

> For `ingest_statsapi.py schedule`, the default window is the **current calendar month only**. Pass `--start-date YYYY-MM-01` to widen the window. Never omit `--start-date` and expect a historical backfill — that requires `--start-date 2015-04-01`.

### dbtf (dbt-fusion)

All dbt commands use `dbtf`, not `dbt`. See `dbt/README.md` for the full command reference.

```bash
dbtf build                                   # build all models + run tests
dbtf build --select mart_odds_events         # build a single model
dbtf test --select mart_odds_events          # run tests for a single model
```

### Snowflake MCP Server (Claude Code in-conversation queries)

The Snowflake MCP server is configured in `.mcp.json` at the repo root. It lets Claude query Snowflake directly during a conversation — no need to switch to snowsql for exploratory questions.

**Package:** `snowflake-labs-mcp` (Snowflake Labs official; run via `uvx`, no persistent install needed)

**Auth:** reads the `[connections.default]` block from `~/.snowsql/config` — same RSA key-pair credential used by snowsql. No credentials in `.mcp.json`.

**Permissions:** read-only. SQL restricted to `SELECT`, `DESCRIBE`, `SHOW`, `USE` via `snowflake_mcp_config.yaml`. Object management and all write operations are blocked.

**Activate:** restart Claude Code after adding `.mcp.json` — the server appears as the `snowflake` MCP tool automatically.

```bash
# Verify the server starts correctly (run manually to test; env vars mirror .mcp.json)
SNOWFLAKE_ACCOUNT="IHUPICS-DP59975" \
SNOWFLAKE_USER="dbt_rw" \
SNOWFLAKE_ROLE="ACCOUNTADMIN" \
SNOWFLAKE_WAREHOUSE="COMPUTE_WH" \
SNOWFLAKE_PRIVATE_KEY_FILE="/Users/charlesclark/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem" \
uvx snowflake-labs-mcp \
  --service-config-file /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/snowflake_mcp_config.yaml
# Expected output: "Initializing tools and resources..." then "Starting MCP server"
# "Closing Snowflake connection" at the end is normal — server shuts down when no client is attached
```

Example queries Claude can run in-conversation once connected:
```sql
-- Feature store coverage check
SELECT game_year, COUNT(*) AS games, SUM(has_full_data::integer) AS full_data_games
FROM baseball_data.betting_features.feature_pregame_game_features
GROUP BY game_year ORDER BY game_year;

-- Quick mart sanity check
SELECT * FROM baseball_data.betting.mart_game_results LIMIT 5;
```

---

### snowsql

Use the `default` named connection with the project RSA key for all ad-hoc Snowflake queries:

```bash
snowsql -c default \
  --private-key-path /Users/charlesclark/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem \
  -q "SELECT * FROM baseball_data.betting.mart_odds_events LIMIT 10;"
```

- `-c default` — selects the `[connections.default]` block in `~/.snowsql/config` (account `IHUPICS-DP59975`, user `dbt_rw`, database `BASEBALL_DATA`)
- `--private-key-path` — RSA private key for key-pair authentication; required because the `dbt_rw` user does not use password auth

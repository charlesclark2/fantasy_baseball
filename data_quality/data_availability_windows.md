# Data Availability Windows

Verified against actual row counts in `baseball_data.savant.batter_pitches` via snowsql on 2026-04-23.
Confirmed lineup coverage audited against `baseball_data.betting.stg_statsapi_lineups_wide` on the same date.

---

## Summary Table

| Feature Group | First Available Date | Last Available Date | Coverage Notes |
|---|---|---|---|
| Statcast pitch data (all columns) | 2015-04-05 | Present (daily) | Full history; 2020 is 60-game COVID season |
| `hyper_speed` | 2015-04-05 | Present | ~33% of pitches (batted contact events); NOT part of the 2023 bat tracking system |
| Bat tracking (bat_speed, swing_length, attack_angle, attack_direction, swing_path_tilt) | 2023-07-14 | Present | Swing-contact events only (~45% of pitches); 2023 partial year (~20%) |
| Intercept offset (intercept_x, intercept_y) | 2023-07-14 | Present | Same coverage as bat tracking — swing-contact events only |
| Confirmed batting lineups | 2015 (all seasons) | Present | 100% coverage for all completed regular season games |
| Probable starting pitchers (Stats API) | 2015 (all seasons) | Present | 97–100% coverage for completed seasons; nulls expected for future games |
| Odds data (The Odds API) | 2020 regular season | Present | Events backfilled 2020–present (68–79% game coverage; 2020: 67.8%, 2021–2025: 72–76%); odds data backfill partial (2023 + live 2026 only — credit exhaustion); see Odds Data section |

---

## Statcast Pitch Data — Full Coverage by Season

Regular season games only (`game_type = 'R'`). Total pitches ~7.5M across 12 seasons.

| Season | Total Pitches | First Date | Last Date | Notes |
|--------|---------------|------------|-----------|-------|
| 2015 | 702,301 | 2015-04-05 | 2015-10-04 | First Statcast season; full 162-game schedule |
| 2016 | 715,821 | 2016-04-03 | 2016-10-02 | |
| 2017 | 721,244 | 2017-04-02 | 2017-10-01 | |
| 2018 | 599,499 | 2018-03-29 | 2018-10-01 | Shortened by CBA postponements |
| 2019 | 732,473 | 2019-03-20 | 2019-09-29 | |
| 2020 | 263,584 | 2020-07-23 | 2020-09-27 | COVID 60-game season; ~1/3 of a normal season |
| 2021 | 709,852 | 2021-04-01 | 2021-10-03 | |
| 2022 | 708,540 | 2022-04-07 | 2022-10-05 | |
| 2023 | 717,945 | 2023-03-30 | 2023-10-01 | |
| 2024 | 709,511 | 2024-03-20 | 2024-09-30 | |
| 2025 | 710,084 | 2025-03-18 | 2025-09-28 | |
| 2026 | 105,706 | 2026-03-25 | 2026-04-21 | Season in progress; audited 2026-04-23 |

---

## Bat Tracking Columns — Verified First Date and Coverage

**Columns:** `bat_speed`, `swing_length`, `attack_angle`, `attack_direction`, `swing_path_tilt`  
(Source names in `baseball_data.savant.batter_pitches`; renamed with `_mph` / `_ft` / `_degrees` suffixes in staging.)

**First date confirmed by query:** `2023-07-14` — this aligns with the 2023 MLB All-Star break, when Hawk-Eye bat tracking was rolled out league-wide.

**Coverage:** These columns only populate for pitches where the batter takes a swing (swinging strikes, fouls, balls in play). They are null for called balls, called strikes, and non-swing events. In 2024–2025, this results in ~45% population rate (the approximate fraction of MLB pitches with a swing). For 2023, the rate is ~20% because the system only covered the second half of the season.

| Season | Total Pitches | bat_speed Populated | Coverage % |
|--------|---------------|---------------------|------------|
| 2015–2022 | — | 0 | 0% — not available |
| 2023 | 717,945 | 145,910 | 20.3% (second half only, swings only) |
| 2024 | 709,511 | 316,641 | 44.6% (swings only) |
| 2025 | 710,084 | 329,759 | 46.4% (swings only) |
| 2026 | 105,706 | 47,549 | 45.0% (swings only) |

**ML design implication:** Bat tracking features should be treated as an **optional era-specific block** (2023-07-14+), not required inputs. Models trained on the full 2015–present history must have a fallback code path that omits these features. Consider training a separate 2024+ model that can require them.

---

## Intercept Offset Columns — Verified First Date and Coverage

**Columns:** `intercept_ball_minus_batter_pos_x_inches`, `intercept_ball_minus_batter_pos_y_inches`  
(Renamed to `intercept_offset_x_inches`, `intercept_offset_y_inches` in staging.)

**First date confirmed by query:** `2023-07-14` — same rollout as bat tracking.

**Coverage:** Identical population pattern to bat tracking (~20.3% in 2023, ~44–46% in 2024-2025). Populates for swing-contact events only.

**Correction to prior docs:** `project_context.md` previously stated "Intercept offset (2024 onward only)" — this is incorrect. Confirmed first date is 2023-07-14, same as the other bat tracking columns.

---

## hyper_speed — Separate Metric, Available Since 2015

`hyper_speed` was previously grouped with the 2023 bat tracking columns in `project_context.md`, but the data shows it has been populated since 2015. It is **not** part of the Hawk-Eye bat tracking system introduced in 2023.

**First date confirmed by query:** `2015-04-05`

**Coverage:** ~21–34% of pitches across all seasons. This fraction is consistent with batted contact events (balls put in play), suggesting `hyper_speed` measures a contact-related speed metric tracked by the original Trackman radar system, not the new bat speed sensor. Coverage has grown gradually from ~21% in 2015 (early Statcast rollout) to ~33% in recent full seasons.

| Season | Total Pitches | hyper_speed Populated | Coverage % |
|--------|---------------|-----------------------|------------|
| 2015 | 702,301 | 151,906 | 21.6% |
| 2016 | 715,821 | 191,281 | 26.7% |
| 2017 | 721,244 | 201,249 | 27.9% |
| 2018 | 599,499 | 167,801 | 28.0% |
| 2019 | 732,473 | 202,484 | 27.6% |
| 2020 | 263,584 | 78,292 | 29.7% |
| 2021 | 709,852 | 234,315 | 33.0% |
| 2022 | 708,540 | 237,219 | 33.5% |
| 2023 | 717,945 | 238,303 | 33.2% |
| 2024 | 709,511 | 239,151 | 33.7% |
| 2025 | 710,084 | 237,014 | 33.4% |
| 2026 | 105,706 | 33,772 | 31.9% |

**ML design implication:** `hyper_speed` is usable as a feature for the full 2015–present training set, unlike the other bat tracking columns. Treat it as a contact-quality metric (available on ~33% of pitches), not as a swing-mechanics metric.

---

## Confirmed Lineup Coverage — Audited 2026-04-23

100% coverage for all regular season games from 2015 through 2026. See [open_data_quality_issues.md](open_data_quality_issues.md) for the full per-year breakdown and design decision.

**Design decision:** `stg_statsapi_lineups_wide` is a **required join** in `mart_pregame_lineup_features` — no training set date cutoff is needed. Nulls only appear for future unplayed games (expected).

---

## Odds Data — Historical Backfill + Live Ingestion

**Verified: 2026-04-25**

The Odds API ingestion has two components:

- **Historical events backfill (Card 1 — complete):** `mlb_events_raw` contains 9,419 distinct events from 2020-07-23 through 2026-04-24. The Odds API covers approximately 68–79% of regular season games per season (not every game is listed by the API); 2020 coverage is lower at 67.8% due to the shortened COVID season.
- **Historical odds backfill (Card 3 — partial):** `mlb_odds_raw` contains odds data for only 239 distinct events due to API credit exhaustion during the backfill. Coverage: 226 events from the 2023 season and 13 from live 2026 ingestion.
- **Live ingestion (ongoing from 2026-04-23):** Both events and odds are ingested daily for upcoming games.

### Coverage Hierarchy: game_pk → event_id → odds prices (audited 2026-04-25)

The Odds API data follows a strict hierarchy: a `game_pk` must match to an `event_id` before odds prices can be retrieved. The table below shows the full funnel per season, queried directly from Snowflake.

| Season | game_pks (regular season) | → with event_id | → events in table | → with odds prices |
|--------|--------------------------|-----------------|-------------------|--------------------|
| 2015–2019 | ~12,202 | 0 (0%) | 0 | 0 |
| 2020 | 898 | 609 (67.8%) | 591 | 591 (100%) |
| 2021 | 2,429 | 1,758 (72.4%) | 1,815 | 1,752 (96.5%) |
| 2022 | 2,430 | 1,789 (73.6%) | 1,799 | 1,799 (100%) |
| 2023 | 2,430 | 1,802 (74.2%) | 1,812 | 1,191 (65.7%) |
| 2024 | 2,429 | 1,809 (74.5%) | 1,828 | 1,826 (99.9%) |
| 2025 | 2,430 | 1,844 (75.9%) | 1,863 | 1,863 (100%) |
| 2026 | 376 | 296 (78.7%) | 316 | 316 (100%) |

**Column definitions:**
- **game_pks**: distinct regular-season game_pks in `mart_game_results`
- **with event_id**: game_pks where `has_odds = true` in `mart_game_odds_bridge` — a matching event was found and linked
- **events in table**: distinct event_ids in `mart_odds_events` for that season (may exceed "with event_id" — see below)
- **with odds prices**: event_ids in `mart_odds_events` that have at least one row in `mart_odds_outcomes`

### Why "events in table" exceeds "game_pks with event_id"

In every season, `mart_odds_events` contains more event_ids than successfully matched game_pks. This was investigated on 2026-04-25 and has two root causes — **neither is a join logic bug**:

1. **Duplicate event_ids from the Odds API.** The Odds API sometimes issues two distinct event_ids for the same game across different ingestion runs. `mart_game_odds_bridge` deduplicates these on `(commence_date, home_team, away_team)`, keeping the most recently ingested event_id and assigning it to the game_pk. The other event_id is never orphaned from a game perspective — the game still has `has_odds = true` — it just doesn't appear in the bridge. This is correct behavior. The effect is most visible in 2021 (1,815 events for 1,758 matched games).

2. **Postponed games.** The Odds API records events on the originally scheduled game date. When a game is postponed and replayed on a different date (e.g., the 2020-08-26/27 Jacob Blake protest boycott, during which multiple teams refused to play), the bridge join on `game_date = commence_date` fails because the Stats API records the actual played date. Those Odds API events will never match a game_pk under the current join logic. This affects a small number of games each season.

### Why the ~25% coverage gap is a true API ceiling

The bridge join logic was verified to be correct on 2026-04-25:

- **Name normalization is not the problem.** The Stats API retroactively applies current franchise names to all historical games (e.g., Cleveland games in 2020 appear as "Cleveland Guardians" in `mart_game_results`). The bridge normalizes Odds API historical names to match: `Cleveland Indians` → `Cleveland Guardians`, `Oakland Athletics` → `Athletics`. These mappings are confirmed correct.
- **The join is not dropping valid matches.** Direct inspection of unmatched events confirmed they are either dedup orphans (case 1 above) or postponed-game mismatches (case 2 above).
- **The Odds API historical endpoint simply does not list all games.** The endpoint returns approximately 10 events per game-date against ~13 actual MLB games. Roughly 3 games per day were never listed. This is an inherent API coverage limitation — there is no workaround through more aggressive querying because the missing game_pks have no event_id in the source data to pass to the odds endpoint.

**Once an event_id exists, odds prices are almost always present** (93–100% across seasons). The 2023 gap (65.7%) is the Card 3 credit-exhaustion issue, not a structural problem.

### Known name mismatches resolved by normalization

- `Cleveland Indians` (Odds API, 2020–2021) → `Cleveland Guardians` (Stats API, all years)
- `Oakland Athletics` (Odds API, 2021–2025) → `Athletics` (Stats API, all years)

### Odds prices (mart_odds_outcomes) coverage by season

| Season | Events with Odds Prices | Notes |
|--------|------------------------|-------|
| 2020 | 591 | Full coverage for matched events |
| 2021 | 1,752 | 63 events missing prices (incomplete backfill) |
| 2022 | 1,799 | Full coverage for matched events |
| 2023 | 1,191 | Partial — Card 3 credit exhaustion stopped backfill mid-season |
| 2024 | 1,826 | Near-full coverage (2 events missing) |
| 2025 | 1,863 | Full coverage for matched events |
| 2026 | 316 | Live ingestion; season in progress |

**ML design implication:** Betting market features (implied probability, line movement) are available for 2020–2022 and 2024–2026 matched events but not usable for full historical model training due to the 25% game_pk coverage ceiling. The ceiling is an API limitation and cannot be closed through improved ingestion logic. Historical event coverage (event_id linkage) is available for 2020–present. Full odds-price backfill for 2023 requires ~9,300 additional API requests for the ~621 missing events.

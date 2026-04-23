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
| Odds data (The Odds API) | 2026-04-23 | Present | Forward-looking only; no historical odds data |

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

## Odds Data — Forward-Looking Only

The Odds API ingestion began **2026-04-23**. No historical odds data exists prior to that date. Odds coverage will grow daily as games are scheduled and ingested.

**ML design implication:** Betting market features (implied probability, line movement) are not usable for historical model training. They are only available for live 2026+ games in the prediction pipeline (Phase 6).

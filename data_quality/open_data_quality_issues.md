Data Quality Issues — Open (baseball_betting_and_fantasy)
All issues below are unresolved. Resolved issues are in `resolved_data_quality_issues_april_2026.md`.

---

## stg_statsapi_lineups_wide — Confirmed Lineup Coverage Audit (Phase 2 pre-work)

**Audit date:** 2026-04-23  
**Status:** No issue — 100% coverage across all seasons. Documented for Phase 2 design reference.

**Diagnostic query:**
```sql
SELECT
    g.game_year,
    COUNT(DISTINCT g.game_pk)                                                                                                   AS total_games,
    COUNT(DISTINCT CASE WHEN lh.game_pk IS NOT NULL THEN g.game_pk END)                                                        AS games_with_home_lineup,
    COUNT(DISTINCT CASE WHEN la.game_pk IS NOT NULL THEN g.game_pk END)                                                        AS games_with_away_lineup,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN lh.game_pk IS NOT NULL THEN g.game_pk END) / NULLIF(COUNT(DISTINCT g.game_pk), 0), 1) AS pct_home_coverage,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN la.game_pk IS NOT NULL THEN g.game_pk END) / NULLIF(COUNT(DISTINCT g.game_pk), 0), 1) AS pct_away_coverage
FROM baseball_data.betting.mart_game_results g
LEFT JOIN baseball_data.betting.stg_statsapi_lineups_wide lh
    ON lh.game_pk = g.game_pk AND lh.home_away = 'home'
LEFT JOIN baseball_data.betting.stg_statsapi_lineups_wide la
    ON la.game_pk = g.game_pk AND la.home_away = 'away'
WHERE g.game_type = 'R'
GROUP BY g.game_year
ORDER BY g.game_year;
```

**Results (regular season games only):**

| game_year | total_games | games_with_home_lineup | games_with_away_lineup | pct_home_coverage | pct_away_coverage |
|-----------|-------------|------------------------|------------------------|-------------------|-------------------|
| 2015      | 2,429       | 2,429                  | 2,429                  | 100.0%            | 100.0%            |
| 2016      | 2,428       | 2,428                  | 2,428                  | 100.0%            | 100.0%            |
| 2017      | 2,430       | 2,430                  | 2,430                  | 100.0%            | 100.0%            |
| 2018      | 2,017       | 2,017                  | 2,017                  | 100.0%            | 100.0%            |
| 2019      | 2,429       | 2,429                  | 2,429                  | 100.0%            | 100.0%            |
| 2020      | 898         | 898                    | 898                    | 100.0%            | 100.0%            |
| 2021      | 2,429       | 2,429                  | 2,429                  | 100.0%            | 100.0%            |
| 2022      | 2,430       | 2,430                  | 2,430                  | 100.0%            | 100.0%            |
| 2023      | 2,430       | 2,430                  | 2,430                  | 100.0%            | 100.0%            |
| 2024      | 2,429       | 2,429                  | 2,429                  | 100.0%            | 100.0%            |
| 2025      | 2,430       | 2,430                  | 2,430                  | 100.0%            | 100.0%            |
| 2026      | 352         | 352                    | 352                    | 100.0%            | 100.0%            |

**Summary finding:** Confirmed lineup data is 100% populated for every regular season game across all 12 seasons in the historical record (2015–2026). There are no seasons with partial coverage — the Stats API includes confirmed batting lineups for all completed games in the `monthly_schedule` payload. The 2020 short season (60 games × 30 teams / 2 = 898 games) and 2018 partial season (2,017 games due to CBA-mandated postponements) show complete coverage within those reduced game totals.

**Design decision:** The ≥70% coverage threshold is met for all seasons without restriction. `mart_pregame_lineup_features` (Phase 2) should treat `stg_statsapi_lineups_wide` as a **required join** (inner join or left join with `NOT NULL` assertion on slot_1_player_id), not an optional feature block. No training set date cutoff is required — lineup features are usable for the full 2015–present historical record. The only expected nulls are for future (unplayed) games where the lineup has not yet been confirmed, which is correct and expected behavior.

---

## mart_game_odds_bridge — Per-Season Match Rate Audit (Phase 1 Enhancement, Card 4)

**Audit date:** 2026-04-23  
**Status:** No test failure — documented for Phase 3/6 design reference.

### Findings

After the historical events backfill (Card 1), the bridge links `mart_game_results` to `mart_odds_events` via `game_date + full team names`. Two team name mismatches between the Odds API (historical names) and Stats API (retroactive canonical names) were identified and fixed in `mart_game_odds_bridge.sql` via a normalization CTE:

- **Cleveland Indians → Cleveland Guardians** — The Stats API retroactively applies "Cleveland Guardians" to all 2021 games; the Odds API preserved the 2021 in-season name "Cleveland Indians". Affected ~135 home + ~51 away = ~186 events in 2021.
- **Oakland Athletics → Athletics** — The Stats API uses "Athletics" retroactively for all seasons; the Odds API used "Oakland Athletics" through 2025. Affected ~93-98 events per season from 2021-2025.

The residual gap after name normalization (~23-26% of games without a matching event) is an Odds API coverage limitation: the historical endpoint returns ~10 events per game-date vs ~13 actual MLB games per day. This cannot be resolved in dbt — it is a source data gap.

### Pre-fix vs post-fix match rates (regular season only)

| Season | Games | Pre-fix matched | Pre-fix % | Post-fix matched | Post-fix % | Δ |
|--------|-------|----------------|-----------|-----------------|-----------|---|
| 2015–2020 | ~14,631 | 0 | 0.0% | 0 | 0.0% | — |
| 2021 | 2,429 | 1,542 | 63.5% | 1,758 | 72.4% | +8.9 pp |
| 2022 | 2,430 | 1,694 | 69.7% | 1,789 | 73.6% | +3.9 pp |
| 2023 | 2,430 | 1,709 | 70.3% | 1,802 | 74.2% | +3.9 pp |
| 2024 | 2,429 | 1,712 | 70.5% | 1,809 | 74.5% | +4.0 pp |
| 2025 | 2,430 | 1,767 | 72.7% | 1,844 | 75.9% | +3.2 pp |
| 2026 | 367 | 287 | 78.2% | 287 | 78.2% | — |

Post-fix values confirmed by `dbtf build` on 2026-04-23.

### Odds API event coverage rate (independent of name fix)

The Odds API returned ~10 events per game-date vs ~13 actual games across all 2021-2025 seasons (~74-77% theoretical maximum match rate):

| Season | Game dates | Total games | Odds events | Odds/Games % |
|--------|-----------|-------------|-------------|--------------|
| 2021 | 182 | 2,429 | 1,815 | 74.7% |
| 2022 | 179 | 2,430 | 1,799 | 74.0% |
| 2023 | 182 | 2,430 | 1,812 | 74.6% |
| 2024 | 185 | 2,429 | 1,828 | 75.3% |
| 2025 | 184 | 2,430 | 1,863 | 76.7% |

### Diagnostic queries

```sql
-- Per-season match rate
SELECT
    YEAR(game_date) AS season,
    COUNT(*) AS total_games,
    SUM(CASE WHEN has_odds THEN 1 ELSE 0 END) AS games_with_odds,
    ROUND(SUM(CASE WHEN has_odds THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS match_pct
FROM baseball_data.betting.mart_game_odds_bridge
WHERE game_type = 'R'
GROUP BY season ORDER BY season;

-- Odds API event coverage vs actual games per season
SELECT
    YEAR(gr.game_date) AS season,
    COUNT(DISTINCT gr.game_pk) AS result_games,
    COUNT(DISTINCT oe.event_id) AS odds_events,
    ROUND(COUNT(DISTINCT oe.event_id) * 100.0 / COUNT(DISTINCT gr.game_pk), 1) AS coverage_pct
FROM baseball_data.betting.mart_game_results gr
LEFT JOIN baseball_data.betting.mart_odds_events oe ON gr.game_date = oe.commence_date
WHERE gr.game_type = 'R' AND YEAR(gr.game_date) BETWEEN 2021 AND 2025
GROUP BY season ORDER BY season;
```

### Design decision

The `has_odds` flag in `mart_game_odds_bridge` signals that an `event_id` exists — it does **not** mean odds prices are present in `mart_odds_outcomes`. For ML/betting use, also check that `mart_odds_outcomes` has rows for that `event_id`. With the partial Card 3 backfill (only 2023 partial + live 2026), odds prices are only usable for live 2026 games until the full odds backfill is completed.

---

## mart_pitch_fielding — Source alignment columns (intentional warns, irresolvable at model layer)

- [ ] `not_null_mart_pitch_fielding_if_fielding_alignment` — if_fielding_alignment has null values (schema.yml:1708)
  - **Findings:** 70,778 of 7,396,560 pitches (0.96%) have null `if_fielding_alignment` in the Statcast source. All are `game_type = 'R'` (regular season). Nulls are a Statcast sensor gap — the alignment tracking system simply did not record data for these pitches. Concentration is highest in early seasons (2015: 4.71%, 2016: 1.89%) and has declined to ~0.1–0.5% in recent years. Cannot be backfilled or corrected — no alignment data exists in the source. Fielder IDs are populated on the same rows, confirming this is an alignment-sensor-specific gap, not a broader tracking failure.
  - **Resolution:** Test intentionally kept at `warn` severity. Cannot be resolved at the model layer — the nulls originate in Baseball Savant's raw data. The nine derived boolean flags (`is_infield_shift`, etc.) now use `coalesce(..., false)` so they are never null; only the raw source strings remain nullable. No further action possible without a source correction from MLB/Statcast.
  - **Resolution Date:** N/A — acknowledged limitation

- [ ] `not_null_mart_pitch_fielding_of_fielding_alignment` — of_fielding_alignment has null values (schema.yml:1718)
  - **Findings:** Same 70,778 rows as `if_fielding_alignment`. Both alignment columns are always null together — there are no pitches where one is null and the other populated. Same root cause and same irresolvable nature.
  - **Resolution:** Test intentionally kept at `warn` severity. Same reasoning as `if_fielding_alignment` above.
  - **Resolution Date:** N/A — acknowledged limitation


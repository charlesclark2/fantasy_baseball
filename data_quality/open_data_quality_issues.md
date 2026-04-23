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

## mart_pitch_fielding — Source alignment columns (intentional warns, irresolvable at model layer)

- [ ] `not_null_mart_pitch_fielding_if_fielding_alignment` — if_fielding_alignment has null values (schema.yml:1708)
  - **Findings:** 70,778 of 7,396,560 pitches (0.96%) have null `if_fielding_alignment` in the Statcast source. All are `game_type = 'R'` (regular season). Nulls are a Statcast sensor gap — the alignment tracking system simply did not record data for these pitches. Concentration is highest in early seasons (2015: 4.71%, 2016: 1.89%) and has declined to ~0.1–0.5% in recent years. Cannot be backfilled or corrected — no alignment data exists in the source. Fielder IDs are populated on the same rows, confirming this is an alignment-sensor-specific gap, not a broader tracking failure.
  - **Resolution:** Test intentionally kept at `warn` severity. Cannot be resolved at the model layer — the nulls originate in Baseball Savant's raw data. The nine derived boolean flags (`is_infield_shift`, etc.) now use `coalesce(..., false)` so they are never null; only the raw source strings remain nullable. No further action possible without a source correction from MLB/Statcast.
  - **Resolution Date:** N/A — acknowledged limitation

- [ ] `not_null_mart_pitch_fielding_of_fielding_alignment` — of_fielding_alignment has null values (schema.yml:1718)
  - **Findings:** Same 70,778 rows as `if_fielding_alignment`. Both alignment columns are always null together — there are no pitches where one is null and the other populated. Same root cause and same irresolvable nature.
  - **Resolution:** Test intentionally kept at `warn` severity. Same reasoning as `if_fielding_alignment` above.
  - **Resolution Date:** N/A — acknowledged limitation


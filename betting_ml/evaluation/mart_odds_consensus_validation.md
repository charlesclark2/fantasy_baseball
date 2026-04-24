# mart_odds_consensus Validation — 2026-04-24

## Summary

All acceptance criteria met. The mart built cleanly, Brier score is within ±0.002 of the
Card 3.11 benchmark, leakage check passed, and both feature models rebuilt with no new
test failures.

---

## Brier Score Benchmark

| Metric | Value | Benchmark | Status |
|---|---|---|---|
| Brier score (2021–2025, has_odds games) | **0.23996** | 0.2395 ± 0.002 | PASS |
| Row count (joined to mart_game_results) | 8,297 | — | — |

Query:
```sql
SELECT
    COUNT(*) AS row_count,
    AVG(POW(c.home_win_prob_consensus - IFF(r.home_team_won, 1.0, 0.0), 2)) AS brier_score
FROM baseball_data.betting.mart_odds_consensus c
JOIN baseball_data.betting.mart_game_odds_bridge b ON b.event_id = c.event_id
JOIN baseball_data.betting.mart_game_results r
    ON r.game_pk = b.game_pk AND r.game_type = 'R'
    AND r.game_year BETWEEN 2021 AND 2025
    AND r.home_team_won IS NOT NULL
WHERE c.home_win_prob_consensus IS NOT NULL
```

---

## Leakage Check

**Result: PASS — 0 leakage rows detected.**

The leakage guard uses `bookmaker_last_update < commence_time` (not `ingestion_ts`). Historical
backfill rows carry `ingestion_ts` = the backfill run date (2026-04-23), not the original
snapshot time, so `ingestion_ts` would incorrectly exclude all historical data. The
`bookmaker_last_update` column is the API-returned timestamp of when the bookmaker last changed
their line and is the correct pre-game proxy. This matches the guard used in
`feature_pregame_odds_features`.

---

## Null Checks

| Column | Null Count | Expected | Status |
|---|---|---|---|
| home_win_prob_consensus | 0 | 0 | PASS |
| home_win_prob_sharp | 1,094 | Non-zero (events with no sharp book coverage) | PASS |
| home_win_prob_soft | 0 | 0 (all events have ≥1 soft book) | PASS |
| market_bookmaker_count | 0 (min = 1, max = 22) | ≥ 1 for all rows | PASS |

Sharp columns (home_win_prob_sharp, home_win_prob_soft, sharp_soft_ml_delta) return `null`, not
`0.0`, when that book group has no coverage for an event — verified by null count above.

---

## Feature Layer Row Count

| Model | Row Count | Prior Baseline | Change |
|---|---|---|---|
| feature_pregame_game_features | 25,155 | 25,146 (2026-04-23) | +9 (new games, expected) |
| feature_pregame_odds_features | 25,155 | 25,146 (2026-04-23) | +9 (new games, expected) |

The +9 row increase reflects one day of 2026 regular season games added since the prior audit.
No rows were dropped by adding the consensus columns — the LEFT JOIN preserves all game_pk rows.

---

## Consensus Coverage in Feature Layer

| Column | Non-null Rows | Notes |
|---|---|---|
| home_win_prob_consensus | 9,202 | Events with ≥1 pre-game h2h bookmaker |
| home_win_prob_sharp | 8,108 | Events with ≥1 sharp book (lowvig/betonlineag/bovada) |
| home_win_prob_soft | 9,202 | Events with ≥1 soft book (dk/fd/betmgm/wh/betrivers) |
| total_line_consensus | 9,154 | Events with ≥1 pre-game totals bookmaker |
| over_prob_consensus | 9,154 | Same as total_line_consensus |

---

## dbt Build Results

```
dbtf build --select mart_odds_consensus feature_pregame_odds_features feature_pregame_game_features

Processed: 3 models | 24 tests (mart) + feature tests
Summary: All success
```

- `mart_odds_consensus`: unique + not_null on event_id — PASS
- `feature_pregame_odds_features`: all 13 existing tests + new model rebuilt — PASS
- `feature_pregame_game_features`: all 9 existing tests — PASS

---

## Card Status

Card 4.7 (mart_odds_consensus) is **complete**. Cards 4.8–4.12 may use
`home_win_prob_consensus`, `ml_consensus_std`, `market_bookmaker_count`,
`total_line_consensus`, and `over_prob_consensus` as training features.

`home_win_prob_sharp`, `home_win_prob_soft`, and `sharp_soft_ml_delta` are present
but flagged as diagnostic columns only (`include_sharp_soft_features = False` per Card 3.11).

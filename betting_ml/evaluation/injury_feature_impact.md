# Injury Feature Impact Report — Card 7.I

**Date generated:** 2026-05-03 (pre-retraining placeholder)  
**Status:** Feature integration complete. Model retraining deferred to Card 7.MA (full batch retraining after all Phase 7 feature expansion).

---

## 1. IL Coverage

> **Note:** Coverage statistics below are placeholders pending historical backfill of `player_transactions` (see Section 5). Run after backfill is complete to populate actual figures.

**Coverage definition:** % of training game-days where ≥1 lineup slot has `is_injured = true` for either team.

| Metric | Value |
|---|---|
| Training game-days total | TBD after backfill |
| Game-days with ≥1 IL player (either team) | TBD |
| Coverage rate | TBD |
| Avg injured_player_count per game-day | TBD |

**Provisional expectation:** IL coverage should be ~30–50% of regular-season game-days based on typical MLB IL activity (each team places 3–5 players on IL at any given time across a 162-game season).

---

## 2. Feature Importance

> Deferred to Card 7.MA post-retraining. Placeholder for expected analysis:

Features added (all three for both home and away sides):

| Feature | Description |
|---|---|
| `home_injured_player_count` / `away_injured_player_count` | Count of IL players in projected lineup (0 when no IL data) |
| `home_injury_adj_avg_woba_30d` / `away_injury_adj_avg_woba_30d` | SUM(woba_30d for healthy slots) / 9.0 — IL slots scored as 0 |
| `home_injury_adj_avg_xwoba_30d` / `away_injury_adj_avg_xwoba_30d` | Same, using xwoba_30d |

**Expected direction:** `injury_adj_avg_woba_30d` should negatively correlate with run-scoring when a team has IL players. Teams with high `avg_woba_30d` but non-zero `injured_player_count` have overstated true offensive strength; the injury-adjusted feature corrects this.

**Key comparison:** `injury_adj_avg_woba_30d` vs `avg_woba_30d` — the delta captures the IL penalty. Higher delta = more significant IL impact on lineup quality.

---

## 3. Row Count Verification

> **Must be verified after next dbt build runs against populated `player_transactions` table.**

The `slot_injury` and `injury_agg` CTEs use LEFT JOINs from the existing `slot_pre_game` grain. They cannot add or remove rows — only add new nullable columns.

**Invariant:** `COUNT(*) FROM feature_pregame_lineup_features` must equal the pre-7.I row count.

Verification query (run before and after first build with IL data):
```sql
SELECT COUNT(*) FROM baseball_data.betting.feature_pregame_lineup_features;
```

---

## 4. Known Limitations

1. **type_code classification confirmed.** The Stats API uses `type_code = 'SC'` (Status Change) for all IL-related events. IL placement vs. activation is determined by `description` text patterns (e.g., `'% on the % injured list%'`, `'% activated%from the % injured list%'`). Confirmed via dry-run output against 2024 season data.

2. **Transactions endpoint may lag same-day IL placements.** IL placements posted on game day may not appear in the API for several hours. The 7-day lookback window in the daily ingestion job captures retroactive placements for prior games but cannot guarantee coverage for same-day decisions made after the daily ingestion run.

3. **Confirmed lineups supersede IL status for game-day predictions.** `has_full_lineup` and the confirmed lineup slots are the authoritative signal for same-day scratches (e.g., late rest days, minor illness). The `injury_adj` features are most valuable at the training-time correction layer and in the pre-lineup window (morning predictions before lineups post).

4. **Historical backfill required for meaningful training signal.** The Stats API transactions endpoint returns data back to at least 2015. Run `scripts/backfill_transactions.py` (see Card 7.I) to populate 2021–2025 before retraining. Without backfill, most training rows will show `injured_player_count = 0`, limiting the feature's learned weight.

5. **No IL data before 2020 via this source.** The Fangraphs injury report Excel files (available in `scripts/raw_files/fangraphs/injury_report/`) cover 2020–present as a human-readable cross-reference but are not machine-ingested. The Stats API transactions endpoint is the authoritative automated source and covers the full training window (2021+).

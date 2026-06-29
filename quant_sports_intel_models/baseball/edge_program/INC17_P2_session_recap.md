# INC-17 P2 Session Recap — Lineup-Gated Feature Null Fix
**Date:** 2026-06-28  
**Model/tier:** Serving fix — do NOT retrain v6  
**Status:** CODE-COMPLETE — operator rebuild + gate pending

---

## Root Cause

Three dbt feature models pull batter lineup slots only from `stg_statsapi_lineups_wide`:

| Model | Null features in feature store |
|---|---|
| `feature_pitcher_cluster_matchups` | `home/away_lineup_avg_woba_vs_cluster`, `*_avg_xwoba_vs_cluster`, `*_cluster_slot_coverage` |
| `feature_pitcher_batter_h2h_matchups` | `home/away_lineup_vs_*_starter_h2h_woba`, `*_h2h_xwoba`, `*_h2h_pa_coverage` |
| `feature_batter_archetype_matchups` | `home/away_lineup_archetype_avg_woba`, `*_avg_xwoba`, `*_slot_coverage`, `*_batter_cluster_mode` |

`stg_statsapi_lineups_wide` contains **historical confirmed lineups (2015–2025) only**. For 2026 games the confirmed lineup lives in the SCD-2 source `feature_pregame_lineup_state`. Since that source was missing, every `slot_*_player_id` in these three models was NULL for all 2026 game_pks → the aggregations return NULL → model receives imputed constants → skill collapses.

Note: `avg_eb_woba` (from `feature_pregame_lineup_features`) was already correctly dual-sourced and shows non-null values — confirmed via Snowflake spot-check. The bug was isolated to the three matchup tables.

Verified in Snowflake:
- `feature_pregame_lineup_features` for 2026-06-28: 15 games, all `has_full_lineup=TRUE`, `avg_eb_woba` populated ✓
- `feature_pitcher_cluster_matchups` for game_pk 822795–823281: `home_lineup_avg_woba_vs_cluster = NULL` for all ✗
- `feature_pregame_game_features` for 2026-06-28: `home_avg_eb_woba` populated ✓, `home_lineup_avg_woba_vs_cluster = NULL` ✗

---

## Fix

Added the dual-source lineup CTE (same pattern as `feature_pregame_lineup_features.sql`) to all three models:

```sql
lineups as (
    -- SCD-2 lineup state (2026+)
    select game_pk, home_away, slot_1..9_player_id
    from {{ source('betting_features', 'feature_pregame_lineup_state') }}
    where is_current = true
    qualify row_number() over (partition by game_pk, home_away order by valid_from desc) = 1

    union all

    -- Historical (2015–2025)
    select game_pk, home_away, slot_1..9_player_id
    from {{ ref('stg_statsapi_lineups_wide') }}
    where game_pk not in (
        select distinct game_pk from {{ source('betting_features', 'feature_pregame_lineup_state') }}
        where is_current = true
    )
),
```

**Files changed:**
- `dbt/models/feature/feature_pitcher_cluster_matchups.sql`
- `dbt/models/feature/feature_pitcher_batter_h2h_matchups.sql`
- `dbt/models/feature/feature_batter_archetype_matchups.sql`

No Python or model weight changes.

---

## CI Status

- **Python fast gate:** 675 passed, 9 skipped ✓
- **dbtf compile:** pre-existing failure in `mart_team_rolling_offense.sql` + `mart_team_rolling_pitching.sql` (E11.1-W5 Jinja `{% else %}` parse error in dbtf-fusion, unrelated to this fix). The three fixed feature models have correct SQL (same pattern as `feature_pregame_lineup_features.sql` which already compiles and runs).

---

## Operator Deploy — Run in Order

All steps are >1 min; hand off to operator.

**Step 1 — Rebuild matchup feature tables (full rebuild, ~3–5 min each):**
```bash
dbtf build --select feature_pitcher_cluster_matchups feature_pitcher_batter_h2h_matchups feature_batter_archetype_matchups
```

**Step 2 — Rebuild feature store for recent window (incremental 7-day, ~5 min):**
```bash
dbtf build --select feature_pregame_game_features_raw feature_pregame_game_features
```

After step 2, spot-check in Snowflake:
```sql
SELECT game_date, game_pk, home_lineup_avg_woba_vs_cluster, home_lineup_vs_away_starter_h2h_woba, home_lineup_archetype_avg_woba
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_date = CURRENT_DATE
ORDER BY game_pk LIMIT 5;
```
Expect non-null values for games with confirmed lineups.

**Step 3 — Rescore 2026-06-23..today as post_lineup backfill to update daily_model_predictions:**
```bash
TARGET_ENV=prod uv run python scripts/predict_today.py --start 2026-06-23 --end 2026-06-27 --is-backfill --prediction-type post_lineup
```
(2026-06-28 will be re-scored by the live post_lineup sensor during the day.)

**Step 4 — Run the health gate:**
```bash
uv run python scripts/ops/model_health_metrics.py --since 2026-06-23 --prediction-type post_lineup --schema betting_ml
```
Gate: `home_win corr ≥ 0.05`. Expected to pass (INC-17 P1 rescored 0.12–0.15 with training-time features; with the three matchup tables now populated the live serving path should recover most of that signal).

---

## git add

```bash
git add dbt/models/feature/feature_pitcher_cluster_matchups.sql
git add dbt/models/feature/feature_pitcher_batter_h2h_matchups.sql
git add dbt/models/feature/feature_batter_archetype_matchups.sql
git add quant_sports_intel_models/baseball/edge_program/build_roadmap.md
git add quant_sports_intel_models/baseball/edge_program/INC17_P2_session_recap.md
```

---

## Open Follow-on (not blocking)

The A2.5 `discriminative_coverage` metric is intentionally blind to lineup-gated feature families (`avg_eb_woba`, cluster matchup, archetype, H2H) because their absence pre-lineup is expected. This means a future null-serving regression in those features won't trigger the degraded-pick alert. Consider adding a post_lineup-specific coverage check that asserts the matchup block is populated for `post_lineup` rows.

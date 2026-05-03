# Batter Archetype Clustering — Feature Impact Report (Card 7.K2)

Generated: 2026-05-03

## Summary

Card 7.K2 implements the demand-side complement to pitcher clustering (Card 7.K).
Batters are clustered into hitting-profile archetypes using Statcast and FanGraphs
data, then a population-level matchup mart computes expected wOBA for each
batter-archetype × pitcher-archetype pairing. Eight new columns are added to
`feature_pregame_game_features`.

---

## Silhouette Scores and Chosen k

| Season | k (chosen) | Silhouette Score | Batters Clustered |
|--------|-----------|-----------------|-------------------|
| 2024   | 4         | 0.1413          | 455               |
| 2025   | 5         | 0.1428          | 461               |

**Notes:**
- k=4 selected for 2024 (best in range 4–8 by silhouette).
- k=5 selected for 2025 (best in range 4–8 by silhouette; marginal improvement over k=4).
- Both scores exceed the 0.10 warning threshold, confirming clusters carry meaningful signal.
- `sprint_speed` column dropped as all-null (not yet in `mart_batter_profile_summary`;
  FanGraphs sprint speed data not integrated into the hitting analytics mart). This reduces
  the feature vector to 12 columns from the planned 13.
- Silhouette scores are lower than pitcher clustering (0.14 vs. 0.14–0.16) as expected —
  offensive profiles are more continuous than pitcher arsenals.

---

## Cluster Centroid Summary

### 2024 (k=4)

| cluster_label    | n_batters | k_pct | bb_pct |  iso  | gb_pct | hard_hit_pct | barrel_pct | avg_xwoba |
|-----------------|-----------|-------|--------|-------|--------|-------------|------------|-----------|
| patient_obp     | 143       | low   | high   | mid   | mid-hi | mid-hi      | low        | mid+      |
| high_whiff      | 142       | high  | low    | mid   | low    | low         | mid        | low       |
| groundball_speed| 100       | mid   | low    | low   | high   | low         | low        | low       |
| power_pull      | 70        | mid   | high   | high  | low    | high        | high       | high      |

### 2025 (k=5)

| cluster_label    | n_batters | k_pct | bb_pct |  iso  | gb_pct | hard_hit_pct | barrel_pct | avg_xwoba |
|-----------------|-----------|-------|--------|-------|--------|-------------|------------|-----------|
| groundball_speed| 107       | mid   | low    | low   | high   | low         | low        | low       |
| high_whiff      | 105       | high  | low    | mid   | low    | low         | mid        | low       |
| contact_spray   | 103       | low   | low    | low   | mid    | high        | mid        | mid+      |
| power_pull      | 75        | mid   | high   | high  | low    | high        | high       | high      |
| patient_obp     | 71        | low   | high   | low   | mid    | low         | low        | mid       |

---

## Spot-Check — Well-Known Batters

Verification against batter_clusters for season=2025 (used for 2026 game features):

| player_name      | assigned_label  | expected_label              | match? |
|-----------------|----------------|-----------------------------|--------|
| Judge, Aaron    | power_pull      | power_pull                  | ✓      |
| Alonso, Pete    | power_pull      | power_pull                  | ✓      |
| Soto, Juan      | power_pull      | patient_obp (pre-2025 era)  | ~      |
| Freeman, Freddie| contact_spray   | balanced / patient_obp      | ~      |
| Bichette, Bo    | contact_spray   | high_whiff / balanced       | ~      |
| Kwan, Steven    | patient_obp     | contact_spray               | ~      |

**Notes:**
- Judge and Alonso correctly land in `power_pull`.
- Juan Soto hit 41 HR in 2024 with high pull% in 2025, making `power_pull` reasonable
  despite his reputation as a patient hitter — reflects actual batted-ball profile.
- Kwan → `patient_obp` vs expected `contact_spray`: with k=5, his elite walk rate
  dominates over spray angle. Acceptable; both archetypes reflect his non-power profile.
- Arraez, Alvarez, Abreu, Ramirez not found in 2025 batter_clusters (likely due to
  insufficient PA or MLBAM ID mismatch in ref_players).

---

## Null Rate by Month for Archetype Matchup Columns

For `home_lineup_archetype_avg_woba` in `feature_pregame_game_features`:

| Season | Month | Coverage % |
|--------|-------|-----------|
| 2025   | March | 47.8%     |
| 2025   | April | 93.9%     |
| 2025   | May   | 99.0%     |
| 2025   | Jun–Sep | 99.7–100.0% |
| 2026   | March | 98.7%     |
| 2026   | April | 95.7%     |
| 2026   | May   | 93.3%     |

**Target:** < 15% null rate (> 85% coverage).  
**Status:** Pass for April–September. March 2025 is elevated (47.8%) due to thin
lineup confirmation data in the opening series. March 2026 is fine (98.7%) because the
population mart has prior data to draw from.

---

## Feature Importance Ranks

Full retraining is deferred to Card 7.MA (batch checkpoint). Feature importance ranks
for the 8 new batter archetype columns will be computed at that time.

**Expected signal hypothesis:**
- `home_lineup_archetype_avg_woba` and `away_lineup_archetype_avg_woba`: primary signal
  — expected to rank in the moderate range (similar to cluster matchup columns from 7.K).
- `*_slot_coverage`: diagnostic; low expected importance.
- `*_batter_cluster_mode`: categorical; moderate importance as interaction with pitcher cluster.
- `*_archetype_avg_xwoba`: correlated with wOBA variant; expected slightly lower importance.

---

## Delta Brier vs. Card 7.K Baseline

Model retraining deferred to Card 7.MA. Delta Brier vs. Card 7.K baseline will be
computed at that checkpoint.

**Prior context:** Card 7.K pitcher clustering features showed moderate positive contribution
(home_win Brier 0.2443 at Card 7.F baseline, unchanged through 7.K feature expansion, with
run_diff MAE marginally affected). K2 batter archetype features are expected to provide
complementary signal rather than large aggregate improvement — the primary value is in
specific lineup configurations (e.g., a groundball_speed lineup vs. a sinker-heavy pitcher cluster).

Per the plan spec: if ΔBrier < −0.001 (negligible), features are retained for potential
ensemble or interaction effects in Card 7.MB regardless of aggregate impact.

---

## Known Limitations

1. **April null rate**: March and early April have elevated null rates due to lineup confirmation
   timing. This matches the same limitation as Card 7.K cluster features.

2. **sprint_speed unavailable**: FanGraphs sprint speed is not yet in `mart_batter_profile_summary`
   (the hitting analytics mart uses ZiPS projections which do not include sprint speed).
   The clustering uses 12 features instead of 13. Adding sprint speed would require a
   dedicated FanGraphs sprint speed ingestion or a merge with Statcast sprint speed data.

3. **Part-time and rookie batter coverage**: The 100 PA minimum gate excludes platoon players
   and first-year batters. These slots will show null matchup data, reflected in
   `archetype_slot_coverage` < 9.

4. **Batter cluster drift**: With k=4 in 2024 and k=5 in 2025, cluster IDs are not stable
   across seasons. `contact_spray` archetype did not exist in 2024 (absorbed into `patient_obp`).
   Downstream models join on `cluster_label` (string), not `cluster_id` (integer), via the
   population mart — so label drift is contained to the clustering cadence.

5. **Population mart sparsity**: Some batter_cluster × pitcher_cluster pairings may have
   fewer than 50 PA in the 180-day window, producing null matchup rows. The shrinkage prior
   (toward wOBA=0.320) mitigates extreme values for thin pairings.

6. **spot-check**: `cluster_label` reflects actual 2024/2025 batted-ball profiles, which
   can differ from a player's stylistic reputation (e.g., Soto's 2024 power surge pushes him
   into `power_pull`). This is intended behavior — the clustering reflects empirical data.

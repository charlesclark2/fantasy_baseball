# Pitcher Cluster Feature Impact Report

**Card:** 7.K — Pitcher Arsenal Clustering
**Status:** To be completed after running cluster_pitchers.py and model retraining

---

## Silhouette Score and Chosen k

| Metric | Value |
|--------|-------|
| Season clustered | TBD |
| k evaluated range | 4–10 |
| Best k | TBD |
| Silhouette score | TBD |

**Threshold:** silhouette > 0.35 required. If best silhouette < 0.35 for all k in 4–10, reduce to k=4.

---

## Cluster Centroid Summary

| cluster_id | cluster_label | n_pitchers | fb_avg_velocity | fastball_pct | breaking_pct | overall_stuff_plus |
|------------|---------------|-----------|----------------|-------------|-------------|-------------------|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |

*Populate after running: `uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --season 2025 --dry-run`*

---

## Spot-Check Table

| Player | cluster_label | Expected |
|--------|--------------|----------|
| Gerrit Cole | TBD | power_swing_and_miss |
| Clayton Kershaw | TBD | elite_breaking_ball |
| Kyle Hendricks | TBD | soft_command or changeup_deceptive |
| Max Scherzer | TBD | power_swing_and_miss or elite_breaking_ball |
| Zack Wheeler | TBD | power_swing_and_miss |
| Spencer Strider | TBD | power_swing_and_miss |
| Logan Webb | TBD | contact_sinker_ball |
| Sandy Alcantara | TBD | contact_sinker_ball |
| Dylan Cease | TBD | elite_breaking_ball |
| Corbin Burnes | TBD | multi_pitch_mix or elite_breaking_ball |

---

## Null Rate for Cluster Coverage Columns

Target: < 10% null for games where both lineups are confirmed (2021+).

| Column | Null rate | Note |
|--------|-----------|------|
| home_lineup_avg_woba_vs_cluster | TBD | Expected high in April (small sample) |
| away_lineup_avg_woba_vs_cluster | TBD | Expected high in April (small sample) |
| home_starter_cluster_id | TBD | Null for pitchers with < 200 pitches in prior season |
| away_starter_cluster_id | TBD | Null for pitchers with < 200 pitches in prior season |

---

## Feature Importance Ranks

*Populate after retraining using validate_feature_selection.py and the XGBoost feature_importances_ output.*

| Column | XGBoost importance rank | Note |
|--------|------------------------|------|
| home_lineup_avg_woba_vs_cluster | TBD | |
| home_lineup_avg_xwoba_vs_cluster | TBD | |
| home_lineup_cluster_slot_coverage | TBD | |
| away_lineup_avg_woba_vs_cluster | TBD | |
| away_lineup_avg_xwoba_vs_cluster | TBD | |
| away_lineup_cluster_slot_coverage | TBD | |
| home_starter_cluster_id | TBD | Categorical |
| away_starter_cluster_id | TBD | Categorical |

---

## ΔBrier / ΔR² vs. Pre-Cluster Baseline

| Model | Baseline (Card 7.J) | With 7.K clusters | Delta | Threshold |
|-------|---------------------|-------------------|-------|-----------|
| home_win (Brier) | TBD | TBD | TBD | < −0.001 = positive contribution |
| total_runs (MAE) | TBD | TBD | TBD | < −0.001 = positive contribution |
| run_differential (MAE) | TBD | TBD | TBD | < −0.001 = positive contribution |

---

## Known Limitations

- **April null rate:** Cluster matchup features will be null for most batters in April because the 30-day rolling window has insufficient PA history and the prior-season clusters lag the current roster.
- **FG crosswalk coverage:** `overall_stuff_plus` is null for pitchers not in the FanGraphs database. Imputed to 100.0 in clustering.
- **2020 availability:** Cluster assignments begin with 2020 season; features using game_year−1 lag mean effective coverage starts 2021.
- **Debut pitchers:** Pitchers with fewer than 200 pitches in the prior season have no cluster assignment; rows will be null in feature_pitcher_cluster_matchups.
- **Cluster stability:** k-means labels are not stable across season re-runs. The human-readable `cluster_label` (via CLUSTER_LABELS dict) provides interpretable continuity.

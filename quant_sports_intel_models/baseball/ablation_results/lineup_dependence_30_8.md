# Story 30.8 — Pre/post-lineup feature classification (Task 1)

Contract union **317**. Class-B (lineup-gated) = **81** features. Method: null-rate over last-3-completed (confirmed) vs next-3-future (unconfirmed) games — tight recent windows to isolate lineup-confirmation from the rolling-window incremental confound. Name cross-check = `L`.

## Pre-lineup contract sizes (Class-A subset = the morning model's inputs)

| target | post-lineup (live) | pre-lineup (Class-A) | Class-B dropped |
|---|---|---|---|
| home_win | 211 | 156 | 55 |
| run_diff | 169 | 126 | 43 |
| total_runs | 113 | 89 | 24 |

## 🔵 Class-B — requires confirmed lineup (81)

| feature | class | null dense/sparse | name? | reason |
|---|---|---|---|---|
| `away_avg_barrel_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_bb_pct_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_bb_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_bb_pct_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_bb_pct` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_iso` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_woba` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_woba_sequential` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_hard_hit_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_hard_hit_pct_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_hard_hit_pct_vs_rhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_k_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_k_pct_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_k_pct_vs_rhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_whiff_rate_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_woba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_woba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_woba_vs_rhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_xwoba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_xwoba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_xwoba_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_catcher_defensive_runs` | B | 0.0/0.0 |  | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 22) |
| `away_injured_player_count` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_archetype_avg_woba` | B | 0.318/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.68) |
| `away_lineup_archetype_pa_coverage` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_avg_attack_angle` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_avg_swing_length` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_avg_woba_vs_cluster` | B | 0.318/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.68) |
| `away_lineup_avg_xwoba_vs_cluster` | B | 0.318/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.68) |
| `away_lineup_bat_speed_vs_starter_velo` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_cluster_slot_coverage` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_iso_vs_starter_archetype` | B | 0.159/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.84) |
| `away_lineup_k_pct_vs_starter_archetype` | B | 0.159/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.84) |
| `away_lineup_vs_home_starter_h2h_xwoba` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_lineup_vs_home_starter_k_pct_adj` | B | 0.159/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.84) |
| `away_lineup_vs_home_starter_xwoba_adj_seasonnorm` | B | 0.0/0.0 | L | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 36) |
| `away_lineup_xwoba_vs_starter_archetype` | B | 0.159/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.84) |
| `away_n_high_whiff` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_n_no_label` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_n_power_pull` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_barrel_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_bb_pct_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_chase_rate_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_bb_pct` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_iso` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_woba` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_woba_sequential` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_hard_hit_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_hard_hit_pct_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_hard_hit_pct_vs_rhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_k_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_k_pct_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_woba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_woba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_woba_vs_rhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_xwoba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_xwoba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_xwoba_vs_lhp` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_away_injury_adj_avg_woba_30d_pct_diff` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_bp_eb_coverage_pct` | B | 0.023/0.0 |  | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 3) |
| `home_catcher_defensive_runs` | B | 0.0/0.0 |  | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 25) |
| `home_injured_player_count` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_archetype_pa_coverage` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_archetype_slot_coverage` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_avg_bat_speed` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_avg_swing_length` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_avg_woba_vs_cluster` | B | 0.068/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.93) |
| `home_lineup_avg_xwoba_vs_cluster` | B | 0.068/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.93) |
| `home_lineup_avg_xwoba_vs_cluster_seasonnorm` | B | 0.0/0.0 | L | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 42) |
| `home_lineup_bat_speed_vs_starter_velo` | B | 0.023/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.98) |
| `home_lineup_iso_vs_starter_archetype` | B | 0.068/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.93) |
| `home_lineup_k_pct_vs_starter_archetype` | B | 0.068/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.93) |
| `home_lineup_vs_away_starter_bb_pct_adj` | B | 0.068/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +0.93) |
| `home_lineup_vs_away_starter_h2h_woba` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_vs_away_starter_h2h_xwoba` | B | 0.0/1.0 | L | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_lineup_vs_away_starter_xwoba_adj_seasonnorm` | B | 0.0/0.0 | L | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 40) |
| `home_n_no_label` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_n_patient_obp` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_n_power_pull` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `ump_accuracy_zscore` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `ump_run_impact_zscore` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |

## ⚠️ name/empirical DISAGREEMENTS — review these (50)

| feature | class | null dense/sparse | name? | reason |
|---|---|---|---|---|
| `away_avg_barrel_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_bb_pct_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_bb_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_bb_pct` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_iso` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_eb_woba` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_hard_hit_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_k_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_whiff_rate_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_woba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_woba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_xwoba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_avg_xwoba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_catcher_defensive_runs` | B | 0.0/0.0 |  | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 22) |
| `away_injured_player_count` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_n_high_whiff` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_n_no_label` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_n_power_pull` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `away_vs_lhp_bb_pct_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 13) |
| `away_vs_lhp_k_pct_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 13) |
| `away_vs_lhp_woba_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 15) |
| `away_vs_lhp_xwoba_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 14) |
| `away_vs_lhp_xwoba_30d_seasonnorm` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 27) |
| `away_vs_lhp_xwoba_std` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 13) |
| `away_vs_rhp_woba_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 13) |
| `home_avg_barrel_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_bb_pct_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_chase_rate_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_bb_pct` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_iso` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_eb_woba` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_hard_hit_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_k_pct_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_woba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_woba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_xwoba_30d` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_avg_xwoba_std` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_away_injury_adj_avg_woba_30d_pct_diff` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_bp_eb_coverage_pct` | B | 0.023/0.0 |  | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 3) |
| `home_catcher_defensive_runs` | B | 0.0/0.0 |  | season-fill placeholder (constant pre-lineup: nunique 1 vs dense 25) |
| `home_injured_player_count` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_n_no_label` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_n_patient_obp` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_n_power_pull` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `home_vs_lhp_slugging_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 15) |
| `home_vs_lhp_woba_std` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 13) |
| `home_vs_lhp_xwoba_std` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 14) |
| `home_vs_rhp_slugging_30d` | A | 0.0/0.0 | L | present pre-lineup (null_sparse 0.00, nunique 15) |
| `ump_accuracy_zscore` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |
| `ump_run_impact_zscore` | B | 0.0/1.0 |  | present-confirmed/absent-unconfirmed (Δnull +1.00) |

_Full per-feature table in the CSV. Class-A = everything not listed Class-B._

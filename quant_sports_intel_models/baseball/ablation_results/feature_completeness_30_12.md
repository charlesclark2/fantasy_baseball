# Story 30.12 — Feature-store completeness map

Contract union: **317** features (2 absent, 131 persistent-gap, 6 early-season, 178 clean).

Mid-season = month ≥ 5; floor tolerance 0.005; early Mar/Apr.

## ⚠ Absent from feature store (100% constant-imputed at serve — serving-skew risk)

| feature | midseason_floor | early_null | gap_seasons |
|---|---|---|---|
| `has_starter_platoon_data` | 1.0 | 1.0 | ALL |
| `is_new_venue` | 1.0 | 1.0 | ALL |

## Persistent mid-season gaps (genuine data gaps — root-cause these)

| feature | midseason_floor | early_null | gap_seasons |
|---|---|---|---|
| `left_ft` | 0.5781 | 0.5907 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_bat_speed_vs_starter_velo` | 0.4831 | 0.458 | 2021,2022,2023,2024,2025,2026 |
| `home_lineup_bat_speed_vs_starter_velo` | 0.4827 | 0.4556 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_avg_attack_angle` | 0.4786 | 0.4496 | 2021,2022,2023,2026 |
| `away_lineup_avg_swing_length` | 0.4786 | 0.4496 | 2021,2022,2023,2026 |
| `home_lineup_avg_bat_speed` | 0.4786 | 0.4496 | 2021,2022,2023,2026 |
| `home_lineup_avg_swing_length` | 0.4786 | 0.4496 | 2021,2022,2023,2026 |
| `away_starter_curveball_stuff_plus` | 0.328 | 0.3365 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_curveball_stuff_plus` | 0.3277 | 0.3445 | 2021,2022,2023,2024,2025,2026 |
| `home_lineup_avg_woba_vs_cluster` | 0.2563 | 0.1423 | 2021,2022,2023,2024,2025,2026 |
| `home_lineup_avg_xwoba_vs_cluster` | 0.2563 | 0.1423 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_archetype_avg_woba` | 0.2549 | 0.1447 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_avg_woba_vs_cluster` | 0.2549 | 0.1447 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_avg_xwoba_vs_cluster` | 0.2549 | 0.1447 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_iso_vs_starter_archetype` | 0.1876 | 0.0855 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_k_pct_vs_starter_archetype` | 0.1876 | 0.0855 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_xwoba_vs_starter_archetype` | 0.1876 | 0.0855 | 2021,2022,2023,2024,2025,2026 |
| `home_lineup_iso_vs_starter_archetype` | 0.1872 | 0.0863 | 2021,2022,2023,2024,2025,2026 |
| `home_lineup_k_pct_vs_starter_archetype` | 0.1872 | 0.0863 | 2021,2022,2023,2024,2025,2026 |
| `away_lineup_vs_home_starter_k_pct_adj` | 0.1646 | 0.0695 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_bb_pct_vs_lhb` | 0.1631 | 0.0695 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_k_pct_vs_lhb` | 0.1631 | 0.0695 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_whiff_rate_vs_lhb` | 0.1631 | 0.0695 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_vs_lhb` | 0.1631 | 0.0695 | 2021,2022,2023,2024,2025,2026 |
| `home_lineup_vs_away_starter_bb_pct_adj` | 0.1629 | 0.0679 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_bb_pct_vs_rhb` | 0.1628 | 0.0687 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_k_pct_vs_rhb` | 0.1628 | 0.0687 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_whiff_rate_vs_rhb` | 0.1628 | 0.0687 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_vs_rhb` | 0.1628 | 0.0687 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_k_pct_vs_lhb` | 0.1615 | 0.0679 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_k_pct_vs_rhb` | 0.1608 | 0.0675 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_whiff_rate_vs_rhb` | 0.1608 | 0.0675 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_xwoba_vs_rhb` | 0.1608 | 0.0675 | 2021,2022,2023,2024,2025,2026 |
| `away_closer_used_prev_1d` | 0.1573 | 0.1958 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_changeup_stuff_plus` | 0.1448 | 0.1691 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_changeup_stuff_plus` | 0.1436 | 0.1647 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_slider_stuff_plus` | 0.1187 | 0.1055 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_trailing_ra9_30g` | 0.0604 | 0.052 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_fip_ra9_gap` | 0.0568 | 0.0556 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_trailing_fip_30g` | 0.0568 | 0.0556 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_trailing_ra9_30g` | 0.0568 | 0.0556 | 2021,2022,2023,2024,2025,2026 |
| `pythagorean_win_exp_diff` | 0.0504 | 0.4017 | 2021,2022,2023,2024 |
| `home_starter_avg_ip_season` | 0.0503 | 0.2366 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_avg_ip_season` | 0.0501 | 0.2378 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_eb_xwoba_against_sequential` | 0.0489 | 0.2366 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_eb_xwoba_against_sequential` | 0.0486 | 0.237 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_csw_pct_3start` | 0.033 | 0.223 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_csw_pct_season` | 0.033 | 0.223 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_csw_pct_season` | 0.0308 | 0.211 | 2021,2022,2023,2024,2025,2026 |
| `away_games_back` | 0.0252 | 0.0576 | 2021,2022,2023,2024 |
| `away_losses` | 0.0252 | 0.0576 | 2021,2022,2023,2024 |
| `away_pythagorean_win_exp` | 0.0252 | 0.3737 | 2021,2022,2023,2024 |
| `away_wins` | 0.0252 | 0.0576 | 2021,2022,2023,2024 |
| `home_games_back` | 0.0252 | 0.056 | 2021,2022,2023,2024 |
| `home_pythagorean_residual_season` | 0.0252 | 0.3761 | 2021,2022,2023,2024 |
| `home_pythagorean_win_exp` | 0.0252 | 0.3761 | 2021,2022,2023,2024 |
| `away_starter_avg_ip_last_3` | 0.0249 | 0.0212 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_avg_ip_last_3` | 0.0238 | 0.0256 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_proj_fip` | 0.0222 | 0.0044 | 2021,2022,2023,2024,2025,2026 |
| `away_closer_used_prev_2d` | 0.0215 | 0.0512 | 2021,2022,2023,2024,2025,2026 |
| `away_high_leverage_used_prev_2d` | 0.0215 | 0.0512 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_proj_fip` | 0.0205 | 0.0044 | 2021,2022,2023,2024,2025,2026 |
| `home_away_starter_k_pct_std_pct_diff` | 0.0203 | 0.0268 | 2021,2022,2023,2024,2025,2026 |
| `park_run_factor_3yr` | 0.02 | 0.0268 | 2021,2025,2026 |
| `runs_per_game_at_park` | 0.02 | 0.0268 | 2021,2025,2026 |
| `home_away_starter_xwoba_against_std_pct_diff` | 0.0191 | 0.024 | 2021,2022,2023,2024,2025,2026 |
| `home_away_bp_xwoba_against_30d_pct_diff` | 0.014 | 0.0496 | 2021,2022,2023,2024,2025,2026 |
| `ump_accuracy_zscore` | 0.012 | 0.0148 | 2023,2024,2025,2026 |
| `ump_run_impact_zscore` | 0.012 | 0.0148 | 2023,2024,2025,2026 |
| `home_starter_barrel_pct_7d` | 0.0107 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_appearances_30d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_barrel_pct_14d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_barrel_pct_30d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_barrel_pct_std` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_batter_chase_rate_7d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_batter_chase_rate_std` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_bb_pct_14d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_bb_pct_30d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_bb_pct_std` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_hard_hit_pct_14d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_hard_hit_pct_30d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_hard_hit_pct_std` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_k_pct_30d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_whiff_rate_14d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_7d_minus_std` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_against_14d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_against_30d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_against_7d` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `home_starter_xwoba_against_std` | 0.0106 | 0.0144 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_batter_chase_rate_30d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_batter_chase_rate_std` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_bb_pct_30d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_bb_pct_7d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_bb_pct_std` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_hard_hit_pct_30d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_hard_hit_pct_7d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_hard_hit_pct_std` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_k_pct_30d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_whiff_rate_14d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_whiff_rate_std` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_xwoba_against_14d` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_starter_xwoba_against_std` | 0.0095 | 0.01 | 2021,2022,2023,2024,2025,2026 |
| `away_bp_eb_coverage_pct` | 0.0083 | 0.0048 | 2021,2022,2023,2024,2025,2026 |
| `away_bp_eb_uncertainty` | 0.0083 | 0.0048 | 2021,2022,2023,2024,2025,2026 |
| `away_bp_eb_xwoba` | 0.0083 | 0.0048 | 2021,2022,2023,2024,2025,2026 |
| `away_team_sequential_bullpen_xwoba` | 0.0083 | 0.0048 | 2021,2022,2023,2024,2025,2026 |
| `left_center_ft` | 0.0081 | 0.0152 | 2021,2025,2026 |
| `right_center_ft` | 0.0081 | 0.0152 | 2021,2025,2026 |
| `away_bp_bb_pct_14d` | 0.0076 | 0.0412 | 2021,2022,2023,2024,2025 |
| `away_bp_bb_pct_30d` | 0.0076 | 0.0412 | 2021,2022,2023,2024,2025 |
| `away_bp_innings_pitched_14d` | 0.0076 | 0.0048 | 2021,2022,2023,2024,2025 |
| `away_bp_innings_pitched_30d` | 0.0076 | 0.0048 | 2021,2022,2023,2024,2025 |
| `away_bp_k_pct_14d` | 0.0076 | 0.0412 | 2021,2022,2023,2024,2025 |
| `away_bp_k_pct_30d` | 0.0076 | 0.0412 | 2021,2022,2023,2024,2025 |
| `away_bp_xwoba_against_14d` | 0.0076 | 0.0412 | 2021,2022,2023,2024,2025 |
| `away_bp_xwoba_against_30d` | 0.0076 | 0.0412 | 2021,2022,2023,2024,2025 |
| `away_bullpen_pitches_prev_7d` | 0.0076 | 0.0416 | 2021,2022,2023,2024,2025 |
| `home_team_sequential_bullpen_xwoba` | 0.0076 | 0.0084 | 2021,2022,2023,2024,2025,2026 |
| `home_bp_eb_coverage_pct` | 0.0075 | 0.0084 | 2021,2022,2023,2024,2025,2026 |
| `home_bp_eb_uncertainty` | 0.0075 | 0.0084 | 2021,2022,2023,2024,2025,2026 |
| `home_bp_eb_xwoba` | 0.0075 | 0.0084 | 2021,2022,2023,2024,2025,2026 |
| `home_bp_hard_hit_pct_14d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_hard_hit_pct_30d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_innings_pitched_30d` | 0.0067 | 0.0084 | 2021,2022,2023,2024,2025 |
| `home_bp_k_pct_14d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_k_pct_30d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_whiff_rate_14d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_whiff_rate_30d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_xwoba_against_14d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `home_bp_xwoba_against_30d` | 0.0067 | 0.044 | 2021,2022,2023,2024,2025 |
| `away_team_oaa_prior_season` | 0.0061 | 0.0064 | 2025 |

## Early-season-by-construction (6 — benign, A2.5 catches)

| feature | midseason_floor | early_null | gap_seasons |
|---|---|---|---|
| `away_woba_against_with_risp_30d` | 0.0 | 0.1315 | - |
| `away_woba_against_with_runners_on_30d` | 0.0 | 0.1315 | - |
| `away_woba_with_risp_30d` | 0.0 | 0.1315 | - |
| `away_xwoba_with_runners_on_30d` | 0.0 | 0.1315 | - |
| `home_woba_against_with_risp_30d` | 0.0 | 0.1255 | - |
| `home_woba_with_risp_30d` | 0.0 | 0.1255 | - |

## Clean: 178 features (no material nulls).

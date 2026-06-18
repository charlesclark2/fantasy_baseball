# Clustered Feature Importance — total_runs (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.4271
- Features: **111** in **98** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 82/98** covering **92/111** features → drop/consolidate candidates (≈83% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C14 | 1 | +0.05450 | [+0.03889, +0.06945] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C15 | 1 | +0.05313 | [+0.03702, +0.06844] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C16 | 1 | +0.01367 | [+0.00471, +0.02261] | ✅ signal | `park_run_factor_3yr` |
| 4 | C4 | 2 | +0.01005 | [+0.00388, +0.01595] | ✅ signal | `home_pit_woba_against_std, home_pit_woba_against_30d` |
| 5 | C0 | 4 | +0.00724 | [+0.00291, +0.01165] | ✅ signal | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_wins, away_losses` |
| 6 | C20 | 1 | +0.00718 | [+0.00104, +0.01386] | ✅ signal | `home_starter_stuff_plus` |
| 7 | C10 | 2 | +0.00432 | [+0.00066, +0.00777] | ✅ signal | `home_off_xwoba_30d, home_team_sequential_woba` |
| 8 | C6 | 2 | +0.00401 | [-0.00056, +0.00830] | 🟡 noise → drop | `away_starter_csw_pct_season, away_starter_csw_pct_3start` |
| 9 | C22 | 1 | +0.00323 | [+0.00042, +0.00602] | ✅ signal | `home_pit_woba_against_14d` |
| 10 | C73 | 1 | +0.00246 | [+0.00038, +0.00467] | ✅ signal | `away_starter_avg_fastball_velo` |
| 11 | C55 | 1 | +0.00204 | [-0.00289, +0.00702] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 12 | C49 | 1 | +0.00198 | [+0.00086, +0.00303] | ✅ signal | `home_starter_avg_ip_season` |
| 13 | C71 | 1 | +0.00193 | [+0.00035, +0.00373] | ✅ signal | `away_lineup_bat_speed_vs_starter_velo` |
| 14 | C63 | 1 | +0.00153 | [-0.00037, +0.00333] | 🟡 noise → drop | `home_avg_woba_30d` |
| 15 | C35 | 1 | +0.00124 | [-0.00000, +0.00241] | 🟡 noise → drop | `away_starter_xwoba_against_std` |
| 16 | C52 | 1 | +0.00117 | [+0.00010, +0.00237] | ✅ signal | `home_starter_whiff_rate_14d` |
| 17 | C69 | 1 | +0.00101 | [+0.00016, +0.00187] | ✅ signal | `away_avg_k_pct_std` |
| 18 | C41 | 1 | +0.00093 | [-0.00081, +0.00261] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 19 | C9 | 2 | +0.00092 | [-0.00279, +0.00506] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 20 | C89 | 1 | +0.00082 | [-0.00161, +0.00336] | 🟡 noise → drop | `home_lineup_avg_bat_speed` |
| 21 | C12 | 2 | +0.00081 | [-0.00201, +0.00367] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 22 | C83 | 1 | +0.00068 | [-0.00004, +0.00141] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 23 | C29 | 1 | +0.00066 | [-0.00141, +0.00266] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 24 | C7 | 2 | +0.00063 | [-0.00057, +0.00182] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj, home_starter_k_pct_vs_rhb` |
| 25 | C51 | 1 | +0.00063 | [-0.00058, +0.00182] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 26 | C25 | 1 | +0.00061 | [-0.00063, +0.00173] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 27 | C90 | 1 | +0.00058 | [-0.00039, +0.00156] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 28 | C56 | 1 | +0.00056 | [-0.00094, +0.00212] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 29 | C62 | 1 | +0.00050 | [-0.00119, +0.00230] | 🟡 noise → drop | `away_vs_lhp_bb_pct_30d` |
| 30 | C78 | 1 | +0.00046 | [-0.00056, +0.00151] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 31 | C11 | 2 | +0.00045 | [-0.00036, +0.00138] | 🟡 noise → drop | `away_bp_bb_pct_30d, away_bp_bb_pct_14d` |
| 32 | C26 | 1 | +0.00036 | [-0.00014, +0.00088] | 🟡 noise → drop | `home_starter_proj_fip` |
| 33 | C57 | 1 | +0.00036 | [-0.00017, +0.00089] | 🟡 noise → drop | `home_lineup_vs_away_starter_xwoba_adj` |
| 34 | C60 | 1 | +0.00035 | [-0.00060, +0.00130] | 🟡 noise → drop | `away_lineup_vs_home_starter_xwoba_adj` |
| 35 | C50 | 1 | +0.00035 | [-0.00043, +0.00119] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 36 | C39 | 1 | +0.00030 | [-0.00001, +0.00061] | 🟡 noise → drop | `away_avg_woba_std` |
| 37 | C13 | 1 | +0.00028 | [-0.00045, +0.00103] | 🟡 noise → drop | `pythagorean_win_exp_diff` |
| 38 | C59 | 1 | +0.00028 | [-0.00101, +0.00164] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 39 | C2 | 2 | +0.00026 | [-0.00083, +0.00134] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 40 | C1 | 2 | +0.00023 | [-0.00122, +0.00162] | 🟡 noise → drop | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 41 | C5 | 2 | +0.00021 | [-0.00130, +0.00139] | 🟡 noise → drop | `away_woba_against_with_runners_on_30d, away_woba_against_with_risp_30d` |
| 42 | C40 | 1 | +0.00020 | [-0.00080, +0.00121] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 43 | C91 | 1 | +0.00017 | [-0.00082, +0.00118] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 44 | C74 | 1 | +0.00013 | [-0.00020, +0.00047] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 45 | C44 | 1 | +0.00011 | [-0.00155, +0.00176] | 🟡 noise → drop | `away_starter_whiff_rate_std` |
| 46 | C84 | 1 | +0.00010 | [-0.00082, +0.00111] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 47 | C18 | 1 | +0.00006 | [-0.00123, +0.00128] | 🟡 noise → drop | `elevation_ft` |
| 48 | C37 | 1 | +0.00005 | [-0.00043, +0.00051] | 🟡 noise → drop | `home_lineup_iso_vs_starter_archetype` |
| 49 | C38 | 1 | +0.00005 | [-0.00082, +0.00091] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 50 | C58 | 1 | +0.00004 | [-0.00007, +0.00015] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 51 | C77 | 1 | +0.00002 | [-0.00003, +0.00008] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 52 | C93 | 1 | +0.00002 | [-0.00099, +0.00109] | 🟡 noise → drop | `home_team_sequential_win_prob` |
| 53 | C30 | 1 | +0.00002 | [-0.00129, +0.00139] | 🟡 noise → drop | `home_lineup_avg_xwoba_vs_cluster` |
| 54 | C70 | 1 | +0.00002 | [-0.00004, +0.00008] | 🟡 noise → drop | `home_pit_hard_hit_pct_30d` |
| 55 | C88 | 1 | +0.00001 | [-0.00003, +0.00005] | 🟡 noise → drop | `away_starter_xwoba_vs_lhb` |
| 56 | C19 | 1 | +0.00000 | [-0.00174, +0.00175] | 🟡 noise → drop | `away_pit_xwoba_against_30d` |
| 57 | C21 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 58 | C23 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 59 | C27 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 60 | C28 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 61 | C32 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 62 | C80 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 63 | C94 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against_sequential` |
| 64 | C95 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 65 | C96 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 66 | C97 | 1 | +0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 67 | C76 | 1 | -0.00000 | [-0.00035, +0.00034] | 🟡 noise → drop | `home_starter_curveball_stuff_plus` |
| 68 | C48 | 1 | -0.00002 | [-0.00067, +0.00062] | 🟡 noise → drop | `away_vs_lhp_xwoba_30d` |
| 69 | C31 | 1 | -0.00002 | [-0.00060, +0.00055] | 🟡 noise → drop | `away_off_runs_per_game_30d` |
| 70 | C42 | 1 | -0.00003 | [-0.00073, +0.00062] | 🟡 noise → drop | `home_starter_xwoba_against_30d` |
| 71 | C81 | 1 | -0.00003 | [-0.00047, +0.00043] | 🟡 noise → drop | `away_bp_innings_pitched_30d` |
| 72 | C79 | 1 | -0.00004 | [-0.00019, +0.00011] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 73 | C36 | 1 | -0.00006 | [-0.00021, +0.00009] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 74 | C65 | 1 | -0.00013 | [-0.00064, +0.00035] | 🟡 noise → drop | `away_catcher_defensive_runs` |
| 75 | C53 | 1 | -0.00014 | [-0.00064, +0.00029] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 76 | C67 | 1 | -0.00014 | [-0.00104, +0.00080] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 77 | C17 | 1 | -0.00015 | [-0.00030, -0.00001] | ✅ signal | `away_pit_k_pct_std` |
| 78 | C72 | 1 | -0.00016 | [-0.00054, +0.00022] | 🟡 noise → drop | `right_center_ft` |
| 79 | C82 | 1 | -0.00016 | [-0.00071, +0.00037] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 80 | C33 | 1 | -0.00024 | [-0.00077, +0.00029] | 🟡 noise → drop | `away_pit_woba_against_7d` |
| 81 | C92 | 1 | -0.00025 | [-0.00111, +0.00056] | 🟡 noise → drop | `away_team_sequential_woba` |
| 82 | C8 | 2 | -0.00025 | [-0.00182, +0.00127] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d, away_xwoba_with_risp_30d` |
| 83 | C66 | 1 | -0.00030 | [-0.00140, +0.00079] | 🟡 noise → drop | `home_starter_slider_stuff_plus` |
| 84 | C24 | 1 | -0.00036 | [-0.00100, +0.00016] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 85 | C68 | 1 | -0.00036 | [-0.00109, +0.00031] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 86 | C61 | 1 | -0.00038 | [-0.00129, +0.00054] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 87 | C3 | 2 | -0.00042 | [-0.00382, +0.00256] | 🟡 noise → drop | `away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 88 | C34 | 1 | -0.00047 | [-0.00136, +0.00036] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 89 | C46 | 1 | -0.00049 | [-0.00144, +0.00037] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 90 | C75 | 1 | -0.00050 | [-0.00141, +0.00036] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 91 | C86 | 1 | -0.00052 | [-0.00196, +0.00092] | 🟡 noise → drop | `away_avg_k_pct_vs_lhp` |
| 92 | C43 | 1 | -0.00055 | [-0.00194, +0.00080] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 93 | C47 | 1 | -0.00072 | [-0.00232, +0.00082] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 94 | C45 | 1 | -0.00078 | [-0.00133, -0.00027] | ✅ signal | `home_off_bb_pct_std` |
| 95 | C64 | 1 | -0.00094 | [-0.00205, +0.00010] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 96 | C85 | 1 | -0.00094 | [-0.00182, -0.00009] | ✅ signal | `away_starter_hard_hit_pct_std` |
| 97 | C87 | 1 | -0.00170 | [-0.00453, +0.00071] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 98 | C54 | 1 | -0.00171 | [-0.00512, +0.00086] | 🟡 noise → drop | `away_pit_bb_pct_7d` |

## Payoff (E1.3 AC)
Dropping the 82 noise clusters (92 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_total_runs_bullpen_v3.json`_
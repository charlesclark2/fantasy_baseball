# Clustered Feature Importance — total_runs (Epic E1.3)

- Recipe: `ngboost-Normal(challenger)` · metric **mae** (lower = better) · pooled baseline 3.4346
- Features: **111** in **98** clusters (`|ρ| ≥ 0.75`), 3 MDA permutations/fold, purged CV (E1.1)
- **Noise clusters (CI crosses 0): 89/98** covering **100/111** features → drop/consolidate candidates (≈90% dimensionality cut with no expected accuracy loss)

Importance = mean OOS **score degradation** when the whole cluster is shuffled together (positive ⇒ destroying the concept hurt accuracy ⇒ real signal). Season-stratified paired-bootstrap 95% CI; a CI entirely above 0 is a signal-bearing concept, a CI crossing 0 is indistinguishable from noise.

| rank | cluster | #feat | importance (Δmae) | 95% CI | verdict | top members |
|---|---|---|---|---|---|---|
| 1 | C14 | 1 | +0.05558 | [+0.03973, +0.07075] | ✅ signal | `home_bp_eb_coverage_pct` |
| 2 | C15 | 1 | +0.05275 | [+0.03681, +0.06820] | ✅ signal | `away_bp_eb_coverage_pct` |
| 3 | C16 | 1 | +0.01137 | [+0.00300, +0.01974] | ✅ signal | `park_run_factor_3yr` |
| 4 | C4 | 2 | +0.01067 | [+0.00354, +0.01718] | ✅ signal | `home_pit_woba_against_std, home_pit_woba_against_30d` |
| 5 | C0 | 4 | +0.00561 | [+0.00169, +0.00990] | ✅ signal | `home_bp_eb_uncertainty, away_bp_eb_uncertainty, away_wins, away_losses` |
| 6 | C6 | 2 | +0.00387 | [-0.00095, +0.00831] | 🟡 noise → drop | `away_starter_csw_pct_season, away_starter_csw_pct_3start` |
| 7 | C22 | 1 | +0.00375 | [+0.00081, +0.00670] | ✅ signal | `home_pit_woba_against_14d` |
| 8 | C10 | 2 | +0.00324 | [-0.00052, +0.00667] | 🟡 noise → drop | `home_off_xwoba_30d, home_team_sequential_woba` |
| 9 | C49 | 1 | +0.00273 | [+0.00149, +0.00388] | ✅ signal | `home_starter_avg_ip_season` |
| 10 | C55 | 1 | +0.00220 | [-0.00310, +0.00757] | 🟡 noise → drop | `home_lineup_bat_speed_vs_starter_velo` |
| 11 | C35 | 1 | +0.00143 | [-0.00007, +0.00288] | 🟡 noise → drop | `away_starter_xwoba_against_std` |
| 12 | C63 | 1 | +0.00140 | [-0.00032, +0.00313] | 🟡 noise → drop | `home_avg_woba_30d` |
| 13 | C29 | 1 | +0.00133 | [-0.00115, +0.00373] | 🟡 noise → drop | `home_starter_trailing_ra9_30g` |
| 14 | C71 | 1 | +0.00131 | [+0.00002, +0.00274] | ✅ signal | `away_lineup_bat_speed_vs_starter_velo` |
| 15 | C73 | 1 | +0.00104 | [-0.00023, +0.00232] | 🟡 noise → drop | `away_starter_avg_fastball_velo` |
| 16 | C12 | 2 | +0.00101 | [-0.00197, +0.00412] | 🟡 noise → drop | `ump_run_impact_zscore, ump_accuracy_zscore` |
| 17 | C25 | 1 | +0.00098 | [-0.00016, +0.00219] | 🟡 noise → drop | `home_away_starter_k_pct_std_pct_diff` |
| 18 | C1 | 2 | +0.00098 | [-0.00072, +0.00262] | 🟡 noise → drop | `home_bp_eb_xwoba, home_team_sequential_bullpen_xwoba` |
| 19 | C26 | 1 | +0.00097 | [+0.00009, +0.00190] | ✅ signal | `home_starter_proj_fip` |
| 20 | C89 | 1 | +0.00091 | [-0.00190, +0.00379] | 🟡 noise → drop | `home_lineup_avg_bat_speed` |
| 21 | C20 | 1 | +0.00087 | [-0.00084, +0.00261] | 🟡 noise → drop | `home_starter_stuff_plus` |
| 22 | C18 | 1 | +0.00085 | [-0.00032, +0.00207] | 🟡 noise → drop | `elevation_ft` |
| 23 | C51 | 1 | +0.00084 | [-0.00028, +0.00192] | 🟡 noise → drop | `away_starter_avg_ip_season` |
| 24 | C56 | 1 | +0.00078 | [-0.00050, +0.00202] | 🟡 noise → drop | `home_starter_changeup_stuff_plus` |
| 25 | C52 | 1 | +0.00077 | [-0.00053, +0.00220] | 🟡 noise → drop | `home_starter_whiff_rate_14d` |
| 26 | C59 | 1 | +0.00068 | [-0.00064, +0.00203] | 🟡 noise → drop | `home_pit_xwoba_against_7d` |
| 27 | C62 | 1 | +0.00061 | [-0.00178, +0.00310] | 🟡 noise → drop | `away_vs_lhp_bb_pct_30d` |
| 28 | C9 | 2 | +0.00056 | [-0.00362, +0.00500] | 🟡 noise → drop | `home_starter_xwoba_against_7d, home_starter_xwoba_7d_minus_std` |
| 29 | C78 | 1 | +0.00053 | [-0.00046, +0.00154] | 🟡 noise → drop | `home_pit_barrel_pct_30d` |
| 30 | C92 | 1 | +0.00053 | [-0.00062, +0.00167] | 🟡 noise → drop | `away_team_sequential_woba` |
| 31 | C57 | 1 | +0.00053 | [-0.00014, +0.00122] | 🟡 noise → drop | `home_lineup_vs_away_starter_xwoba_adj` |
| 32 | C11 | 2 | +0.00052 | [-0.00022, +0.00128] | 🟡 noise → drop | `away_bp_bb_pct_30d, away_bp_bb_pct_14d` |
| 33 | C44 | 1 | +0.00042 | [-0.00101, +0.00200] | 🟡 noise → drop | `away_starter_whiff_rate_std` |
| 34 | C42 | 1 | +0.00038 | [-0.00040, +0.00118] | 🟡 noise → drop | `home_starter_xwoba_against_30d` |
| 35 | C83 | 1 | +0.00036 | [-0.00041, +0.00112] | 🟡 noise → drop | `home_bp_hard_hit_pct_14d` |
| 36 | C8 | 2 | +0.00030 | [-0.00110, +0.00171] | 🟡 noise → drop | `away_xwoba_with_runners_on_30d, away_xwoba_with_risp_30d` |
| 37 | C60 | 1 | +0.00030 | [-0.00019, +0.00078] | 🟡 noise → drop | `away_lineup_vs_home_starter_xwoba_adj` |
| 38 | C69 | 1 | +0.00030 | [-0.00019, +0.00079] | 🟡 noise → drop | `away_avg_k_pct_std` |
| 39 | C82 | 1 | +0.00024 | [-0.00038, +0.00086] | 🟡 noise → drop | `home_woba_with_risp_30d` |
| 40 | C41 | 1 | +0.00023 | [-0.00129, +0.00174] | 🟡 noise → drop | `away_starter_k_pct_vs_rhb` |
| 41 | C39 | 1 | +0.00023 | [-0.00017, +0.00062] | 🟡 noise → drop | `away_avg_woba_std` |
| 42 | C81 | 1 | +0.00019 | [-0.00029, +0.00070] | 🟡 noise → drop | `away_bp_innings_pitched_30d` |
| 43 | C37 | 1 | +0.00018 | [-0.00033, +0.00064] | 🟡 noise → drop | `home_lineup_iso_vs_starter_archetype` |
| 44 | C30 | 1 | +0.00016 | [-0.00105, +0.00146] | 🟡 noise → drop | `home_lineup_avg_xwoba_vs_cluster` |
| 45 | C67 | 1 | +0.00015 | [-0.00051, +0.00085] | 🟡 noise → drop | `home_off_barrel_pct_30d` |
| 46 | C7 | 2 | +0.00011 | [-0.00109, +0.00135] | 🟡 noise → drop | `away_lineup_vs_home_starter_k_pct_adj, home_starter_k_pct_vs_rhb` |
| 47 | C74 | 1 | +0.00010 | [-0.00044, +0.00065] | 🟡 noise → drop | `home_pit_hard_hit_pct_7d` |
| 48 | C5 | 2 | +0.00010 | [-0.00140, +0.00127] | 🟡 noise → drop | `away_woba_against_with_runners_on_30d, away_woba_against_with_risp_30d` |
| 49 | C58 | 1 | +0.00009 | [-0.00009, +0.00027] | 🟡 noise → drop | `home_bp_xwoba_against_30d` |
| 50 | C76 | 1 | +0.00008 | [-0.00012, +0.00034] | 🟡 noise → drop | `home_starter_curveball_stuff_plus` |
| 51 | C48 | 1 | +0.00008 | [-0.00073, +0.00085] | 🟡 noise → drop | `away_vs_lhp_xwoba_30d` |
| 52 | C84 | 1 | +0.00005 | [-0.00097, +0.00115] | 🟡 noise → drop | `home_bp_hard_hit_pct_30d` |
| 53 | C93 | 1 | +0.00003 | [-0.00048, +0.00053] | 🟡 noise → drop | `home_team_sequential_win_prob` |
| 54 | C88 | 1 | +0.00003 | [-0.00004, +0.00010] | 🟡 noise → drop | `away_starter_xwoba_vs_lhb` |
| 55 | C50 | 1 | +0.00002 | [-0.00046, +0.00050] | 🟡 noise → drop | `away_avg_woba_vs_rhp` |
| 56 | C77 | 1 | +0.00000 | [-0.00012, +0.00012] | 🟡 noise → drop | `home_bp_xwoba_against_14d` |
| 57 | C21 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_k_pct` |
| 58 | C23 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_woba` |
| 59 | C27 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_avg_eb_iso` |
| 60 | C28 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_k_pct` |
| 61 | C32 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_avg_eb_iso` |
| 62 | C80 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_uncertainty` |
| 63 | C94 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `home_starter_eb_xwoba_against_sequential` |
| 64 | C95 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `away_starter_eb_xwoba_against_sequential` |
| 65 | C96 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `has_starter_platoon_data` |
| 66 | C97 | 1 | -0.00000 | [-0.00000, +0.00000] | 🟡 noise → drop | `is_new_venue` |
| 67 | C79 | 1 | -0.00000 | [-0.00019, +0.00021] | 🟡 noise → drop | `away_avg_k_pct_vs_rhp` |
| 68 | C36 | 1 | -0.00001 | [-0.00029, +0.00027] | 🟡 noise → drop | `away_off_bb_pct_std` |
| 69 | C91 | 1 | -0.00003 | [-0.00127, +0.00120] | 🟡 noise → drop | `away_starter_hard_hit_pct_7d` |
| 70 | C70 | 1 | -0.00003 | [-0.00022, +0.00015] | 🟡 noise → drop | `home_pit_hard_hit_pct_30d` |
| 71 | C65 | 1 | -0.00005 | [-0.00042, +0.00031] | 🟡 noise → drop | `away_catcher_defensive_runs` |
| 72 | C38 | 1 | -0.00006 | [-0.00076, +0.00059] | 🟡 noise → drop | `away_off_hard_hit_pct_std` |
| 73 | C90 | 1 | -0.00008 | [-0.00126, +0.00109] | 🟡 noise → drop | `home_starter_barrel_pct_std` |
| 74 | C17 | 1 | -0.00010 | [-0.00023, +0.00002] | 🟡 noise → drop | `away_pit_k_pct_std` |
| 75 | C75 | 1 | -0.00016 | [-0.00063, +0.00031] | 🟡 noise → drop | `away_bullpen_pitches_prev_7d` |
| 76 | C2 | 2 | -0.00019 | [-0.00097, +0.00061] | 🟡 noise → drop | `away_bp_eb_xwoba, away_team_sequential_bullpen_xwoba` |
| 77 | C68 | 1 | -0.00025 | [-0.00086, +0.00029] | 🟡 noise → drop | `away_off_hard_hit_pct_7d` |
| 78 | C40 | 1 | -0.00027 | [-0.00202, +0.00160] | 🟡 noise → drop | `home_starter_k_pct_vs_lhb` |
| 79 | C19 | 1 | -0.00028 | [-0.00131, +0.00079] | 🟡 noise → drop | `away_pit_xwoba_against_30d` |
| 80 | C46 | 1 | -0.00028 | [-0.00127, +0.00071] | 🟡 noise → drop | `home_pit_k_pct_7d` |
| 81 | C33 | 1 | -0.00028 | [-0.00097, +0.00034] | 🟡 noise → drop | `away_pit_woba_against_7d` |
| 82 | C31 | 1 | -0.00030 | [-0.00091, +0.00027] | 🟡 noise → drop | `away_off_runs_per_game_30d` |
| 83 | C72 | 1 | -0.00030 | [-0.00069, +0.00010] | 🟡 noise → drop | `right_center_ft` |
| 84 | C86 | 1 | -0.00033 | [-0.00184, +0.00114] | 🟡 noise → drop | `away_avg_k_pct_vs_lhp` |
| 85 | C13 | 1 | -0.00037 | [-0.00129, +0.00056] | 🟡 noise → drop | `pythagorean_win_exp_diff` |
| 86 | C45 | 1 | -0.00038 | [-0.00096, +0.00018] | 🟡 noise → drop | `home_off_bb_pct_std` |
| 87 | C3 | 2 | -0.00039 | [-0.00375, +0.00261] | 🟡 noise → drop | `away_pythagorean_win_exp, away_team_sequential_win_prob` |
| 88 | C53 | 1 | -0.00041 | [-0.00108, +0.00019] | 🟡 noise → drop | `away_lineup_iso_vs_starter_archetype` |
| 89 | C34 | 1 | -0.00041 | [-0.00147, +0.00059] | 🟡 noise → drop | `home_starter_k_pct_30d` |
| 90 | C24 | 1 | -0.00044 | [-0.00157, +0.00038] | 🟡 noise → drop | `home_pit_k_pct_std` |
| 91 | C61 | 1 | -0.00052 | [-0.00147, +0.00046] | 🟡 noise → drop | `home_catcher_defensive_runs` |
| 92 | C47 | 1 | -0.00056 | [-0.00196, +0.00080] | 🟡 noise → drop | `home_woba_against_with_risp_30d` |
| 93 | C66 | 1 | -0.00066 | [-0.00222, +0.00091] | 🟡 noise → drop | `home_starter_slider_stuff_plus` |
| 94 | C43 | 1 | -0.00068 | [-0.00294, +0.00149] | 🟡 noise → drop | `home_starter_csw_pct_season` |
| 95 | C85 | 1 | -0.00069 | [-0.00160, +0.00025] | 🟡 noise → drop | `away_starter_hard_hit_pct_std` |
| 96 | C64 | 1 | -0.00110 | [-0.00251, +0.00027] | 🟡 noise → drop | `home_starter_batter_chase_rate_std` |
| 97 | C87 | 1 | -0.00173 | [-0.00489, +0.00091] | 🟡 noise → drop | `home_avg_k_pct_vs_lhp` |
| 98 | C54 | 1 | -0.00246 | [-0.00656, +0.00067] | 🟡 noise → drop | `away_pit_bb_pct_7d` |

## Payoff (E1.3 AC)
Dropping the 89 noise clusters (100 features) is the dimensionality cut to verify value-preserving: re-run the promotion gate (`promotion_gate_eval.py --purged-cv`) on the pruned contract and confirm no accuracy regression beyond the noise floor before promoting the smaller set.

_JSON: `betting_ml/evaluation/feature_selection/clustered_importance/clustered_importance_total_runs_bullpen_v3_stuffplus_deleaked.json`_
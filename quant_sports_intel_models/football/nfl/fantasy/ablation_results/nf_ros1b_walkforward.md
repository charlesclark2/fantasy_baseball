# NF-ROS1b walk-forward (hurdle interval)

Generated 2026-09-17T06:02:04+00:00 · commit `b8d98343` · folds [2020, 2021, 2022, 2023, 2024, 2025] · registration `nf_ros1b_preregistration.md` + amendment 1, inheriting `nf_ros1_preregistration.md` + amendments 1–2.

**Winner (pooled full-PPR CRPS):** `eb_rate_avail` · field PBO 0.0 (precondition < 0.2: PASS) · flips {'eb_rate_avail': 3, 'eb_rate': 3}

| arm | pooled mean CRPS |
|---|---|
| `eb_rate` | 14.5816 |
| `eb_avail` | 15.4779 |
| `eb_rate_avail` | 14.3714 |

## Per position (gate: full-PPR 12-team)

| pos | mean lift | folds won | p | DSR | foil lift | cov80 / floor | PIT dev | ships |
|---|---|---|---|---|---|---|---|---|
| QB | +1.5795 | 6/6 | 0.0062 | 0.9943 | +3.7750 | 0.799 / 0.773 | 0.0336 | no |
| RB | +1.5255 | 6/6 | 0.0012 | 0.9949 | +3.2742 | 0.859 / 0.780 | 0.0054 | **YES** |
| WR | +1.0440 | 6/6 | 0.0002 | 0.9376 | +2.7874 | 0.869 / 0.785 | 0.0089 | no |
| TE | +0.6172 | 6/6 | 0.0041 | 0.4509 | +2.1347 | 0.875 / 0.779 | 0.0078 | no |
| K | +0.3581 | 4/6 | 0.1569 | 0.6955 | +1.5205 | 0.772 / 0.759 | 0.0569 | no |

### Clauses

- **QB**: FAILED C8a_oracle_floor → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)
- **RB**: all pass
- **WR**: FAILED C4_dsr_ok, C8a_oracle_floor → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)
- **TE**: FAILED C4_dsr_ok, C8a_oracle_floor → `CONSTRAINT_REFUSED` (classify_null: `DSR_UNREACHABLE`)
- **K**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)

### Channel 2×2 (reported, never recombined)

| pos | rate | avail | both | interaction |
|---|---|---|---|---|
| QB | +0.6835 | +0.1596 | +1.5795 | +0.7364 |
| RB | +0.8893 | +0.3096 | +1.5255 | +0.3265 |
| WR | +1.1575 | -0.2997 | +1.0440 | +0.1862 |
| TE | +0.7904 | -0.0353 | +0.6172 | -0.1378 |
| K | +0.0061 | +0.3439 | +0.3581 | +0.0081 |

### Degenerates (pooled CRPS; must exceed the winner)

- QB: winner 20.619 · frozen_full 22.268 · naive_pace 23.208 · last3_pace 23.504 · nihilist_zero 54.015 · zero_width 29.660 · max_width 109.398 · max_width cov80 0.956
- RB: winner 15.174 · frozen_full 16.843 · naive_pace 16.834 · last3_pace 17.174 · nihilist_zero 40.213 · zero_width 21.798 · max_width 121.867 · max_width cov80 0.996
- WR: winner 13.908 · frozen_full 15.030 · naive_pace 15.158 · last3_pace 15.639 · nihilist_zero 37.246 · zero_width 20.013 · max_width 112.261 · max_width cov80 0.999
- TE: winner 10.172 · frozen_full 10.780 · naive_pace 11.552 · last3_pace 11.882 · nihilist_zero 26.278 · zero_width 13.815 · max_width 81.740 · max_width cov80 0.999
- K: winner 14.665 · frozen_full 15.678 · naive_pace 16.995 · last3_pace 17.420 · nihilist_zero 55.242 · zero_width 18.706 · max_width 45.126 · max_width cov80 0.997

### Strata (mean CRPS lift over incumbent, per row)

k1 +0.612 · k2 +0.932 · k3 +1.070 · k4 +1.233 · k5 +1.263 · k6 +1.369 · k7 +1.381 · k8 +1.338 · k9 +1.213 · k10 +1.041 · k11 +0.921 · k12 +0.753 · rookie +3.265 · veteran +0.854

## Waiver replacement (§7)

State: **INACTIVE** — only 1 position(s) ship the value

## Diagnostics

```
{
 "seasons": {
  "2019": {
   "board_rows": 745,
   "by_id": 528,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 217,
   "doubly_claimed_dropped": 0
  },
  "2020": {
   "board_rows": 771,
   "by_id": 579,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 192,
   "doubly_claimed_dropped": 0
  },
  "2021": {
   "board_rows": 787,
   "by_id": 607,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 180,
   "doubly_claimed_dropped": 0
  },
  "2022": {
   "board_rows": 812,
   "by_id": 599,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 213,
   "doubly_claimed_dropped": 0
  },
  "2023": {
   "board_rows": 789,
   "by_id": 560,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 229,
   "doubly_claimed_dropped": 0
  },
  "2024": {
   "board_rows": 772,
   "by_id": 576,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 196,
   "doubly_claimed_dropped": 0
  },
  "2025": {
   "board_rows": 817,
   "by_id": 594,
   "by_name": 0,
   "ambiguous_dropped": 0,
   "no_realized_row": 223,
   "doubly_claimed_dropped": 0
  }
 },
 "unresolved_team_rows": 0,
 "player_seasons": 5493,
 "league_median_basis_rows": 2083,
 "pace_capped_player_seasons": 76,
 "off_board_realized_share_full_ppr": {
  "2019": 0.03778219024827555,
  "2020": 0.02453428411698705,
  "2021": 0.02168225602715416,
  "2022": 0.03166330583882277,
  "2023": 0.0282257494650788,
  "2024": 0.011682040091956346,
  "2025": 0.02037854988906187
 },
 "scoring_terms": {
  "standard": {
   "applied": [
    "fg_made_0_39",
    "fg_made_40_49",
    "fg_made_50_plus",
    "fumbles_lost",
    "pass_int",
    "pass_td",
    "pass_yds",
    "pat_made",
    "rec_td",
    "rec_yds",
    "rush_td",
    "rush_yds"
   ],
   "captured": [
    "def_blocked_kick",
    "def_fumble_rec",
    "def_int",
    "def_sacks",
    "def_safety",
    "def_td",
    "dst_pa_g_0",
    "dst_pa_g_14_17",
    "dst_pa_g_1_6",
    "dst_pa_g_28_34",
    "dst_pa_g_35_45",
    "dst_pa_g_46p",
    "dst_pa_g_7_13",
    "st_td",
    "two_pt"
   ]
  },
  "half_ppr": {
   "applied": [
    "fg_made_0_39",
    "fg_made_40_49",
    "fg_made_50_plus",
    "fumbles_lost",
    "pass_int",
    "pass_td",
    "pass_yds",
    "pat_made",
    "rec",
    "rec_td",
    "rec_yds",
    "rush_td",
    "rush_yds"
   ],
   "captured": [
    "def_blocked_kick",
    "def_fumble_rec",
    "def_int",
    "def_sacks",
    "def_safety",
    "def_td",
    "dst_pa_g_0",
    "dst_pa_g_14_17",
    "dst_pa_g_1_6",
    "dst_pa_g_28_34",
    "dst_pa_g_35_45",
    "dst_pa_g_46p",
    "dst_pa_g_7_13",
    "st_td",
    "two_pt"
   ]
  },
  "full_ppr": {
   "applied": [
    "fg_made_0_39",
    "fg_made_40_49",
    "fg_made_50_plus",
    "fumbles_lost",
    "pass_int",
    "pass_td",
    "pass_yds",
    "pat_made",
    "rec",
    "rec_td",
    "rec_yds",
    "rush_td",
    "rush_yds"
   ],
   "captured": [
    "def_blocked_kick",
    "def_fumble_rec",
    "def_int",
    "def_sacks",
    "def_safety",
    "def_td",
    "dst_pa_g_0",
    "dst_pa_g_14_17",
    "dst_pa_g_1_6",
    "dst_pa_g_28_34",
    "dst_pa_g_35_45",
    "dst_pa_g_46p",
    "dst_pa_g_7_13",
    "st_td",
    "two_pt"
   ]
  }
 }
}
```

## NF-ROS1b hurdle readings (§5 reference, §7 diagnostics — never gates)

### `reference_only_winner_at_location_shift` — **reference only — not a trial, not in V, gates nothing**

| pos | hurdle cov80 | hurdle PIT dev | hurdle CRPS | ref cov80 | ref PIT dev | ref CRPS |
|---|---|---|---|---|---|---|
| QB | 0.799 | 0.0336 | 20.619 | 0.740 | 0.1329 | 21.127 |
| RB | 0.859 | 0.0054 | 15.174 | 0.802 | 0.0963 | 15.489 |
| WR | 0.869 | 0.0089 | 13.908 | 0.811 | 0.0912 | 14.037 |
| TE | 0.875 | 0.0078 | 10.172 | 0.806 | 0.0999 | 10.289 |
| K | 0.772 | 0.0569 | 14.665 | 0.732 | 0.0820 | 14.396 |

### Mechanism check (top tercile: q05 = 0 share vs realized zero share; lowest PIT decile)

| pos | construction | q05=0 share | realized zero share | lowest decile |
|---|---|---|---|---|
| QB | hurdle | 0.352 | 0.064 | 0.130 |
| RB | hurdle | 0.162 | 0.042 | 0.105 |
| WR | hurdle | 0.378 | 0.044 | 0.092 |
| TE | hurdle | 0.395 | 0.030 | 0.094 |
| K | hurdle | 0.021 | 0.009 | 0.114 |
| QB | location_shift_reference | 0.275 | 0.064 | 0.228 |
| RB | location_shift_reference | 0.370 | 0.042 | 0.196 |
| WR | location_shift_reference | 0.394 | 0.044 | 0.193 |
| TE | location_shift_reference | 0.529 | 0.030 | 0.196 |
| K | location_shift_reference | 0.004 | 0.009 | 0.176 |

The registered §7 prediction (the hurdle's q05 = 0 share falls toward the realized zero share) is kept as written. A q05 = 0 share is not a calibration reading: q05 = 0 exactly when P(zero) ≥ 0.05 (amendment 2).

### POST-SMOKE COMPANION DIAGNOSTIC — top-tercile atom calibration (gates nothing; not a clause, not in V/PBO/DSR, not in any verdict)

| pos | top-tercile rows | mean predicted P(zero) | realized zero share | difference |
|---|---|---|---|---|
| QB | 2488 | 0.075 | 0.064 | +0.012 |
| RB | 4380 | 0.043 | 0.042 | +0.001 |
| WR | 7184 | 0.064 | 0.044 | +0.020 |
| TE | 3812 | 0.073 | 0.030 | +0.042 |
| K | 1128 | 0.023 | 0.009 | +0.014 |

### π reliability (10 equal-count bins: predicted → realized)

- QB: 0.03→0.01 · 0.04→0.02 · 0.07→0.07 · 0.18→0.19 · 0.36→0.36 · 0.49→0.46 · 0.57→0.57 · 0.65→0.60 · 0.74→0.62 · 0.85→0.71
- RB: 0.01→0.01 · 0.02→0.01 · 0.03→0.03 · 0.05→0.06 · 0.12→0.15 · 0.31→0.31 · 0.53→0.56 · 0.65→0.69 · 0.76→0.76 · 0.88→0.85
- WR: 0.02→0.01 · 0.03→0.03 · 0.06→0.05 · 0.09→0.09 · 0.17→0.18 · 0.37→0.33 · 0.64→0.62 · 0.78→0.77 · 0.88→0.84 · 0.95→0.89
- TE: 0.02→0.01 · 0.03→0.01 · 0.05→0.04 · 0.09→0.08 · 0.16→0.17 · 0.33→0.30 · 0.58→0.55 · 0.74→0.76 · 0.86→0.87 · 0.95→0.93
- K: 0.01→0.01 · 0.02→0.01 · 0.02→0.01 · 0.02→0.01 · 0.02→0.00 · 0.04→0.04 · 0.20→0.27 · 0.61→0.58 · 0.76→0.67 · 0.89→0.76

### Counts

```
{
 "QB": {
  "rows": 7464,
  "y_negative_rows": 329,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.3616023579849946,
  "mean_pi": 0.3965845668439588
 },
 "RB": {
  "rows": 13140,
  "y_negative_rows": 47,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.34421613394216133,
  "mean_pi": 0.3382672265432185
 },
 "WR": {
  "rows": 21552,
  "y_negative_rows": 20,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.379779138827023,
  "mean_pi": 0.3994996022327797
 },
 "TE": {
  "rows": 11436,
  "y_negative_rows": 0,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.3717208814270724,
  "mean_pi": 0.3798410226029033
 },
 "K": {
  "rows": 3384,
  "y_negative_rows": 0,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.23433806146572103,
  "mean_pi": 0.25934412980095795
 }
}
{"n": 180, "single_class": 0, "dropped_features": 36}
```

### Strata C9 (informative only — C9 gates pooled per position)

k1 0.013 · k2 0.010 · k3 0.012 · k4 0.008 · k5 0.007 · k6 0.005 · k7 0.012 · k8 0.009 · k9 0.006 · k10 0.011 · k11 0.010 · k12 0.011 · rookie 0.082 · veteran 0.007

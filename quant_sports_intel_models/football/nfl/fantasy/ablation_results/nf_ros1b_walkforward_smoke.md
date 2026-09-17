# NF-ROS1b walk-forward (hurdle interval) — SMOKE (code-path proof, never a gate)

Generated 2026-09-17T05:54:29+00:00 · commit `41cbb3e3` · folds [2020, 2021] · registration `nf_ros1b_preregistration.md` + amendment 1, inheriting `nf_ros1_preregistration.md` + amendments 1–2.

**Winner (pooled full-PPR CRPS):** `eb_rate_avail` · field PBO None (precondition < 0.2: FAIL) · flips {'eb_rate_avail': 2}

| arm | pooled mean CRPS |
|---|---|
| `eb_rate` | 15.3685 |
| `eb_avail` | 15.8896 |
| `eb_rate_avail` | 14.8153 |

## Per position (gate: full-PPR 12-team)

| pos | mean lift | folds won | p | DSR | foil lift | cov80 / floor | PIT dev | ships |
|---|---|---|---|---|---|---|---|---|
| QB | +1.8659 | 2/2 | None | None | +5.9462 | 0.814 / 0.755 | 0.0302 | no |
| RB | +1.9648 | 2/2 | None | None | +4.2148 | 0.835 / 0.764 | 0.0217 | no |
| WR | +1.3363 | 2/2 | None | None | +3.7023 | 0.859 / 0.773 | 0.0159 | no |
| TE | +0.7996 | 2/2 | None | None | +2.9231 | 0.889 / 0.762 | 0.0132 | no |
| K | +0.7641 | 2/2 | None | None | +1.9141 | 0.698 / 0.732 | 0.1053 | no |

### Clauses

- **QB**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C8b_matched_n → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **RB**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **WR**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **TE**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **K**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C7_coverage_floor, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)

### Channel 2×2 (reported, never recombined)

| pos | rate | avail | both | interaction |
|---|---|---|---|---|
| QB | -0.0271 | +1.0330 | +1.8659 | +0.8601 |
| RB | +0.8682 | +0.7187 | +1.9648 | +0.3778 |
| WR | +1.2522 | -0.0343 | +1.3363 | +0.1184 |
| TE | +0.9025 | +0.0046 | +0.7996 | -0.1075 |
| K | +0.1432 | +0.6657 | +0.7641 | -0.0448 |

### Degenerates (pooled CRPS; must exceed the winner)

- QB: winner 18.718 · frozen_full 20.054 · naive_pace 21.077 · last3_pace 21.611 · nihilist_zero 54.510 · zero_width 27.178 · max_width 107.783 · max_width cov80 0.960
- RB: winner 16.576 · frozen_full 18.695 · naive_pace 17.944 · last3_pace 18.484 · nihilist_zero 41.098 · zero_width 23.462 · max_width 121.819 · max_width cov80 0.997
- WR: winner 14.979 · frozen_full 16.392 · naive_pace 16.014 · last3_pace 16.371 · nihilist_zero 39.111 · zero_width 21.265 · max_width 99.936 · max_width cov80 1.000
- TE: winner 10.020 · frozen_full 10.722 · naive_pace 11.063 · last3_pace 11.624 · nihilist_zero 25.546 · zero_width 13.418 · max_width 76.597 · max_width cov80 0.998
- K: winner 14.299 · frozen_full 15.492 · naive_pace 15.880 · last3_pace 16.492 · nihilist_zero 50.665 · zero_width 18.537 · max_width 43.249 · max_width cov80 0.997

### Strata (mean CRPS lift over incumbent, per row)

k1 +0.822 · k2 +1.224 · k3 +1.537 · k4 +1.633 · k5 +1.712 · k6 +1.765 · k7 +1.627 · k8 +1.599 · k9 +1.542 · k10 +1.238 · k11 +1.169 · k12 +0.963 · rookie +3.910 · veteran +1.134

## Waiver replacement (§7)

State: **INACTIVE** — only 0 position(s) ship the value

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
  }
 },
 "unresolved_team_rows": 0,
 "player_seasons": 2303,
 "league_median_basis_rows": 936,
 "pace_capped_player_seasons": 38,
 "off_board_realized_share_full_ppr": {
  "2019": 0.03778219024827555,
  "2020": 0.02453428411698705,
  "2021": 0.02168225602715416
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
| QB | 0.814 | 0.0302 | 18.718 | 0.778 | 0.1372 | 19.000 |
| RB | 0.835 | 0.0217 | 16.576 | 0.771 | 0.0950 | 17.233 |
| WR | 0.859 | 0.0159 | 14.979 | 0.793 | 0.0975 | 15.087 |
| TE | 0.889 | 0.0132 | 10.020 | 0.810 | 0.1055 | 9.993 |
| K | 0.698 | 0.1053 | 14.299 | 0.701 | 0.0976 | 14.145 |

### Mechanism check (top tercile: q05 = 0 share vs realized zero share; lowest PIT decile)

| pos | construction | q05=0 share | realized zero share | lowest decile |
|---|---|---|---|---|
| QB | hurdle | 0.488 | 0.058 | 0.112 |
| RB | hurdle | 0.151 | 0.044 | 0.100 |
| WR | hurdle | 0.404 | 0.046 | 0.092 |
| TE | hurdle | 0.595 | 0.039 | 0.096 |
| K | hurdle | 0.067 | 0.015 | 0.144 |
| QB | location_shift_reference | 0.196 | 0.058 | 0.227 |
| RB | location_shift_reference | 0.358 | 0.044 | 0.199 |
| WR | location_shift_reference | 0.380 | 0.046 | 0.202 |
| TE | location_shift_reference | 0.576 | 0.039 | 0.206 |
| K | location_shift_reference | 0.000 | 0.015 | 0.205 |

The registered §7 prediction (the hurdle's q05 = 0 share falls toward the realized zero share) is kept as written. A q05 = 0 share is not a calibration reading: q05 = 0 exactly when P(zero) ≥ 0.05 (amendment 2).

### POST-SMOKE COMPANION DIAGNOSTIC — top-tercile atom calibration (gates nothing; not a clause, not in V/PBO/DSR, not in any verdict)

| pos | top-tercile rows | mean predicted P(zero) | realized zero share | difference |
|---|---|---|---|---|
| QB | 832 | 0.091 | 0.058 | +0.033 |
| RB | 1424 | 0.040 | 0.044 | -0.004 |
| WR | 2344 | 0.063 | 0.046 | +0.017 |
| TE | 1244 | 0.092 | 0.039 | +0.054 |
| K | 388 | 0.029 | 0.015 | +0.014 |

### π reliability (10 equal-count bins: predicted → realized)

- QB: 0.03→0.01 · 0.05→0.02 · 0.08→0.04 · 0.23→0.26 · 0.45→0.39 · 0.58→0.46 · 0.67→0.53 · 0.75→0.56 · 0.82→0.66 · 0.90→0.74
- RB: 0.01→0.02 · 0.02→0.01 · 0.03→0.04 · 0.05→0.06 · 0.10→0.12 · 0.24→0.24 · 0.48→0.41 · 0.64→0.58 · 0.76→0.69 · 0.89→0.81
- WR: 0.02→0.01 · 0.03→0.04 · 0.06→0.06 · 0.10→0.09 · 0.17→0.16 · 0.32→0.28 · 0.58→0.54 · 0.77→0.73 · 0.89→0.80 · 0.96→0.86
- TE: 0.03→0.01 · 0.05→0.02 · 0.07→0.05 · 0.11→0.10 · 0.19→0.20 · 0.36→0.31 · 0.58→0.54 · 0.75→0.73 · 0.87→0.88 · 0.95→0.95
- K: 0.01→0.00 · 0.01→0.02 · 0.02→0.03 · 0.02→0.00 · 0.03→0.02 · 0.05→0.06 · 0.25→0.29 · 0.69→0.59 · 0.84→0.68 · 0.94→0.71

### Counts

```
{
 "QB": {
  "rows": 2496,
  "y_negative_rows": 98,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.36738782051282054,
  "mean_pi": 0.4561461638192219
 },
 "RB": {
  "rows": 4272,
  "y_negative_rows": 12,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.2979868913857678,
  "mean_pi": 0.3204608104419378
 },
 "WR": {
  "rows": 7032,
  "y_negative_rows": 0,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.3565130830489192,
  "mean_pi": 0.38952590175413604
 },
 "TE": {
  "rows": 3732,
  "y_negative_rows": 0,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.3783494105037513,
  "mean_pi": 0.3960983214751801
 },
 "K": {
  "rows": 1164,
  "y_negative_rows": 0,
  "point_zero_rows": 0,
  "point_zero_realized_zero_share": null,
  "realized_zero_share": 0.23883161512027493,
  "mean_pi": 0.28574365967157894
 }
}
{"n": 60, "single_class": 0, "dropped_features": 12}
```

### Strata C9 (informative only — C9 gates pooled per position)

k1 0.027 · k2 0.027 · k3 0.035 · k4 0.022 · k5 0.016 · k6 0.011 · k7 0.023 · k8 0.020 · k9 0.013 · k10 0.023 · k11 0.020 · k12 0.013 · rookie 0.074 · veteran 0.014

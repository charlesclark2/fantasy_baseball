# NF-ROS1b parent reproduction (location-shift)

Generated 2026-09-17T06:18:05+00:00 · commit `b8d98343` · folds [2020, 2021, 2022, 2023, 2024, 2025] · registration `nf_ros1b_preregistration.md` + amendment 1, inheriting `nf_ros1_preregistration.md` + amendments 1–2.

**Winner (pooled full-PPR CRPS):** `eb_rate_avail` · field PBO 0.0 (precondition < 0.2: PASS) · flips {'eb_rate_avail': 6}

| arm | pooled mean CRPS |
|---|---|
| `eb_rate` | 16.5696 |
| `eb_avail` | 15.9603 |
| `eb_rate_avail` | 14.5773 |

## Per position (gate: full-PPR 12-team)

| pos | mean lift | folds won | p | DSR | foil lift | cov80 / floor | PIT dev | ships |
|---|---|---|---|---|---|---|---|---|
| QB | +3.3675 | 6/6 | 0.0025 | 0.9999 | +3.4126 | 0.740 / 0.773 | 0.1329 | no |
| RB | +3.4996 | 6/6 | 0.0 | 0.9957 | +3.5051 | 0.802 / 0.780 | 0.0963 | no |
| WR | +3.2383 | 6/6 | 0.0003 | 0.9994 | +3.2453 | 0.811 / 0.785 | 0.0912 | no |
| TE | +2.4276 | 6/6 | 0.0001 | 0.9989 | +2.3588 | 0.806 / 0.779 | 0.0999 | no |
| K | +1.7960 | 6/6 | 0.0026 | 0.9007 | +1.7895 | 0.732 / 0.759 | 0.0820 | no |

### Clauses

- **QB**: FAILED C7_coverage_floor, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)
- **RB**: FAILED C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)
- **WR**: FAILED C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)
- **TE**: FAILED C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)
- **K**: FAILED C4_dsr_ok, C7_coverage_floor, C8a_oracle_floor, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `POWER_LIMITED`)

### Channel 2×2 (reported, never recombined)

| pos | rate | avail | both | interaction |
|---|---|---|---|---|
| QB | +0.9795 | +1.2724 | +3.3675 | +1.1155 |
| RB | +0.9657 | +2.1078 | +3.4996 | +0.4261 |
| WR | +1.3439 | +1.5431 | +3.2383 | +0.3513 |
| TE | +1.0835 | +1.7008 | +2.4276 | -0.3567 |
| K | +0.0373 | +1.7824 | +1.7960 | -0.0237 |

### Degenerates (pooled CRPS; must exceed the winner)

- QB: winner 21.140 · frozen_full 26.565 · naive_pace 23.461 · last3_pace 23.914 · nihilist_zero 38.746 · zero_width 29.660 · max_width 109.398 · max_width cov80 0.956
- RB: winner 15.488 · frozen_full 19.828 · naive_pace 18.207 · last3_pace 18.815 · nihilist_zero 28.602 · zero_width 21.798 · max_width 121.867 · max_width cov80 0.996
- WR: winner 14.065 · frozen_full 18.168 · naive_pace 16.461 · last3_pace 17.270 · nihilist_zero 26.790 · zero_width 20.013 · max_width 112.261 · max_width cov80 0.999
- TE: winner 10.285 · frozen_full 13.342 · naive_pace 12.424 · last3_pace 13.009 · nihilist_zero 19.009 · zero_width 13.815 · max_width 81.740 · max_width cov80 0.999
- K: winner 14.391 · frozen_full 17.336 · naive_pace 18.297 · last3_pace 19.042 · nihilist_zero 24.412 · zero_width 18.706 · max_width 45.126 · max_width cov80 0.997

### Strata (mean CRPS lift over incumbent, per row)

k1 +2.016 · k2 +3.040 · k3 +3.339 · k4 +3.418 · k5 +3.454 · k6 +3.511 · k7 +3.453 · k8 +3.380 · k9 +3.212 · k10 +2.925 · k11 +2.668 · k12 +2.309 · rookie +5.660 · veteran +2.774

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

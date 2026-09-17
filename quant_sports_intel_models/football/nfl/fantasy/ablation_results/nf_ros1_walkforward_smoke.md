# NF-ROS1 walk-forward — SMOKE (code-path proof, never a gate)

Generated 2026-09-17T04:33:03+00:00 · commit `316c42e5` · folds [2020, 2021] · registration `nf_ros1_preregistration.md` + amendments 1–2.

**Winner (pooled full-PPR CRPS):** `eb_rate_avail` · field PBO None (precondition < 0.2: FAIL) · flips {'eb_rate_avail': 2}

| arm | pooled mean CRPS |
|---|---|
| `eb_rate` | 17.7264 |
| `eb_avail` | 16.4796 |
| `eb_rate_avail` | 15.0218 |

## Per position (gate: full-PPR 12-team)

| pos | mean lift | folds won | p | DSR | foil lift | cov80 / floor | PIT dev | ships |
|---|---|---|---|---|---|---|---|---|
| QB | +4.4562 | 2/2 | None | None | +5.3293 | 0.778 / 0.755 | 0.1372 | no |
| RB | +3.9141 | 2/2 | None | None | +3.9285 | 0.771 / 0.764 | 0.0950 | no |
| WR | +4.3052 | 2/2 | None | None | +4.3318 | 0.793 / 0.773 | 0.0975 | no |
| TE | +2.9959 | 2/2 | None | None | +2.9959 | 0.810 / 0.762 | 0.1055 | no |
| K | +2.0261 | 2/2 | None | None | +1.9943 | 0.701 / 0.732 | 0.0976 | no |

### Clauses

- **QB**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C8b_matched_n, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **RB**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **WR**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **TE**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)
- **K**: FAILED C2_fold_consistency, C3_significant_bh, C4_dsr_ok, C5_beats_matched_foil, C7_coverage_floor, C9_pit_flat → `CONSTRAINT_REFUSED` (classify_null: `UNDEFINED`)

### Channel 2×2 (reported, never recombined)

| pos | rate | avail | both | interaction |
|---|---|---|---|---|
| QB | +0.1505 | +2.8467 | +4.4562 | +1.4591 |
| RB | +0.8812 | +2.4849 | +3.9141 | +0.5480 |
| WR | +1.7246 | +2.3312 | +4.3052 | +0.2493 |
| TE | +1.2143 | +2.1539 | +2.9959 | -0.3724 |
| K | +0.2594 | +1.8917 | +2.0261 | -0.1250 |

### Degenerates (pooled CRPS; must exceed the winner)

- QB: winner 19.000 · frozen_full 24.699 · naive_pace 21.694 · last3_pace 22.395 · nihilist_zero 39.408 · zero_width 27.178 · max_width 107.783 · max_width cov80 0.960
- RB: winner 17.200 · frozen_full 22.492 · naive_pace 19.604 · last3_pace 20.411 · nihilist_zero 27.550 · zero_width 23.462 · max_width 121.819 · max_width cov80 0.997
- WR: winner 15.087 · frozen_full 19.981 · naive_pace 17.125 · last3_pace 17.889 · nihilist_zero 27.442 · zero_width 21.265 · max_width 99.936 · max_width cov80 1.000
- TE: winner 9.994 · frozen_full 13.241 · naive_pace 12.363 · last3_pace 13.135 · nihilist_zero 18.519 · zero_width 13.418 · max_width 76.597 · max_width cov80 0.998
- K: winner 14.157 · frozen_full 16.797 · naive_pace 16.544 · last3_pace 17.346 · nihilist_zero 23.958 · zero_width 18.537 · max_width 43.249 · max_width cov80 0.997

### Strata (mean CRPS lift over incumbent, per row)

k1 +2.712 · k2 +3.979 · k3 +4.455 · k4 +4.445 · k5 +4.356 · k6 +4.383 · k7 +4.251 · k8 +4.160 · k9 +3.945 · k10 +3.428 · k11 +3.110 · k12 +2.705 · rookie +6.660 · veteran +3.523

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

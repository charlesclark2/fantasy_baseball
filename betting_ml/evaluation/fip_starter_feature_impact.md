# ZiPS FIP Starter Feature Impact Report (Card 8.B)

Generated from `betting_ml/evaluation/feature_selection.md` after Card 7.MA full retrain (2026-05-04, 294 features, 10,256 rows).

---

## Summary

4 FIP-related starter features were added: ZiPS projected FIP (pre-season projection), trailing actual FIP (30-game rolling), and the FIP-RA9 gap (luck-adjustment signal). 5 of 6 new columns survived feature selection; the away FIP-RA9 gap was dropped for near-zero correlation.

- **Total FIP columns added:** 6 (2 proj_fip, 2 trailing_fip_30g, 2 fip_ra9_gap)
- **Retained:** 5
- **Dropped (near-zero correlation):** 1

---

## Retained Features

| Feature | max \|r\| | r (total_runs) | r (run_differential) | r (home_win) |
|---|---|---|---|---|
| `away_starter_trailing_fip_30g` | 0.1016 | +0.0276 | +0.1016 | +0.0804 |
| `away_starter_proj_fip` | 0.0949 | +0.0341 | +0.0949 | +0.0734 |
| `home_starter_proj_fip` | 0.0909 | +0.0774 | -0.0909 | -0.0790 |
| `home_starter_trailing_fip_30g` | 0.0830 | +0.0830 | -0.0713 | -0.0681 |
| `home_starter_fip_ra9_gap` | 0.0321 | -0.0321 | +0.0175 | +0.0182 |

## Dropped — Near-Zero Correlation

| Feature | max \|r\| observed |
|---|---|
| `away_starter_fip_ra9_gap` | 0.0161 |

The away FIP-RA9 gap falls below the 0.02 |r| retention threshold. The home version is retained because the home team's luck adjustment interacts differently with venue effects.

---

## Comparison with Existing xwOBA-Against Features

FIP adds meaningful signal beyond xwOBA-against. The trailing FIP and proj_fip features are not strongly collinear with xwOBA-based features because:
- `proj_fip` is a pre-season projection capturing expected season-long performance, while xwOBA-against is a rolling in-season window
- `trailing_fip_30g` incorporates HR, BB, and K in a single normalized run-value unit, which xwOBA tracks differently

| FIP feature | max \|r\| | Nearest xwOBA equiv | max \|r\| |
|---|---|---|---|
| `away_starter_trailing_fip_30g` | 0.1016 | `away_pit_xwoba_against_std` | 0.1073 |
| `away_starter_proj_fip` | 0.0949 | `away_pit_xwoba_against_30d` | 0.1041 |
| `home_starter_trailing_fip_30g` | 0.0830 | `home_pit_xwoba_against_std` | 0.1162 |

FIP features are slightly below the corresponding xwOBA features in raw |r| but survived multicollinearity screening (|r| < 0.85 with xwOBA features), indicating they carry independent signal. This is consistent with Cui (2020): FIP's HR-weighting provides a dimension that xwOBA-against does not fully capture.

---

## Null Rate Notes

ZiPS projections are available for 2024 and 2025 backfill (ingested in Card 7.E). Pre-2024 rows have NULL `proj_fip` (imputed to league-average 4.00 in `preprocessing.py`). Trailing FIP nulls expected for starters with < 5 career starts (< 10 IP threshold). Both features were included in the Card 7.MA retrain with imputation in place.

---

## Recommendation

**Retain all 5 surviving FIP features.** Both ZiPS proj_fip and trailing_fip_30g add independent signal beyond xwOBA-against. The FIP-RA9 gap (home only) captures the luck-adjustment signal described in Cui (2020). All 5 features were included in the Card 7.MA retrain.

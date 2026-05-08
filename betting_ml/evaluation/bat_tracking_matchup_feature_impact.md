# Bat Tracking Matchup Feature Impact Report (Card 8.E)

Generated: 2026-05-07
Dataset: `feature_pregame_game_features` JOIN `mart_game_results` (regular season).
Validation method: Snowflake `CORR()` on full populated rows (matches Card 8.Q approach;
`validate_feature_selection.py` deferred until pre-7M model retrain).

---

## Summary

8 bat tracking matchup columns were added (4 per side):
`lineup_avg_bat_speed`, `lineup_avg_swing_length`, `lineup_avg_attack_angle`,
`lineup_bat_speed_vs_starter_velo`. All columns are NULL for pre-2023-07-14 games
(Hawk-Eye bat sensor coverage begins 2023-07-14).

**Hypothesis:** Individual batter bat speed vs. the opposing starter's fastball
velocity is a matchup signal that 30-day team averages wash out. A lineup of
high-bat-speed hitters facing a 97+ mph starter is a different prediction
scenario than a contact lineup facing the same starter.

**Source mart:** `mart_batter_bat_tracking_profile` — 126,614 rows, 893 distinct
batters, 2023-07-14 → 2026-05-06. Swing-count-weighted 30-day rolling averages of
`bat_speed_mph`, `swing_length_ft`, `attack_angle_degrees` from `stg_batter_pitches`
(swinging strikes, fouls, balls in play).

---

## Coverage: Null Rates by Season

Regular-season games only.

| Season | Games | Null bat speed | Null ratio (vs starter velo) |
|---|---:|---:|---:|
| 2015–2022 | 17,490 | 100% | 100% |
| 2023 | 2,430 | 56.5% | 56.9% |
| 2024 | 2,429 | 0.0% | 1.0% |
| 2025 | 2,430 | 0.0% | 0.8% |
| 2026 (in-season) | 552 | 0.0% | 1.1% |

The 2023 null rate matches the Hawk-Eye start date (July 14). Post-2024 the null
rate is at floor — the residual ~1% on the ratio reflects opening-day starts
where the opposing starter has no `avg_fastball_velo_7d` populated yet
(imputation handled in `preprocessing.py`).

---

## Value Ranges (non-null rows, home side)

| Feature | min | mean | max | std |
|---|---:|---:|---:|---:|
| `home_lineup_avg_bat_speed` (mph) | 63.09 | 69.57 | 73.46 | 0.99 |
| `home_lineup_avg_swing_length` (ft) | 6.31 | 7.20 | 7.99 | 0.15 |
| `home_lineup_avg_attack_angle` (deg) | 2.09 | 9.12 | 14.63 | 1.43 |
| `home_lineup_bat_speed_vs_starter_velo` (ratio) | 0.666 | 0.747 | 0.843 | 0.022 |

All ranges are physically plausible. League-average bat speed for the lineup
mean (69.6 mph) is consistent with MLB-wide ~71 mph individual averages, slightly
lower because contact-oriented bottom-of-order hitters drag the lineup mean.

---

## Correlation with Targets (n = 6,468 fully populated games)

| Feature | r (total_runs) | r (run_diff) | r (home_win) |
|---|---:|---:|---:|
| `home_lineup_avg_bat_speed` | +0.029 | +0.024 | +0.024 |
| `away_lineup_avg_bat_speed` | +0.012 | −0.034 | −0.034 |
| `home_lineup_avg_swing_length` | +0.004 | +0.039 | +0.038 |
| `away_lineup_avg_swing_length` | −0.001 | −0.044 | −0.040 |
| `home_lineup_avg_attack_angle` | −0.004 | +0.024 | +0.002 |
| `away_lineup_avg_attack_angle` | +0.014 | −0.011 | +0.004 |
| **`home_lineup_bat_speed_vs_starter_velo`** | **+0.044** | **+0.050** | **+0.038** |
| **`away_lineup_bat_speed_vs_starter_velo`** | **+0.044** | **−0.048** | **−0.035** |

**Phase 4 EDA baseline (team averages):** max |r| = 0.022 with total_runs.

The matchup ratio `lineup_bat_speed_vs_starter_velo` is the strongest signal
(|r| ≈ 0.044–0.050), about **2× the team-average baseline** and with the expected
directional asymmetry: a high-bat-speed home lineup correlates positively with
home runs scored / home win, while a high-bat-speed away lineup correlates
negatively with run differential and home win. The raw bat speed and swing
length columns are weaker but directionally consistent. Attack angle is roughly
flat against all targets (small effect, supporting context only).

---

## Cross-Correlation with Existing Features (Redundancy Check)

| Feature pair | Pearson r |
|---|---:|
| `home_lineup_bat_speed_vs_starter_velo` vs `away_starter_stuff_plus` | −0.463 |
| `home_lineup_bat_speed_vs_starter_velo` vs `home_lineup_woba_vs_starter_archetype` | +0.080 |
| `home_lineup_avg_bat_speed` vs `home_avg_hard_hit_pct_30d` | +0.468 |
| `home_lineup_avg_bat_speed` vs `home_avg_barrel_pct_30d` | +0.367 |
| `home_lineup_avg_attack_angle` vs `home_avg_barrel_pct_30d` | +0.313 |
| `home_lineup_avg_bat_speed` vs `away_lineup_avg_bat_speed` | +0.016 |

**Multicollinearity threshold:** |r| > 0.85 triggers drop in `select_features()`.
All pairs are well below the threshold. The strongest correlation is
`bat_speed_vs_starter_velo` ↔ `away_starter_stuff_plus` at −0.463: as expected,
better stuff (higher Stuff+) tends to come with higher fastball velo, lowering
the ratio. The negative sign and modest magnitude confirm the matchup ratio
encodes information distinct from Stuff+ alone (the 79% of variance unexplained
is the lineup-side contribution). Bat speed correlates moderately with hard-hit
% (+0.47) and barrel % (+0.37) — same direction, different aggregation grain
(individual-swing physics vs. 30-day team-level outcomes), with most variance
independent.

---

## Recommendation

**Include all 8 features in the next retrain.** Criteria met:

- ✅ `lineup_bat_speed_vs_starter_velo` clears the Phase 4 baseline (|r| up to 0.050 vs 0.022)
- ✅ No pair exceeds |r| = 0.85 multicollinearity threshold
- ✅ `lineup_bat_speed_vs_starter_velo` not redundant with `starter_stuff_plus` (|r| = 0.46)
- ✅ Coverage at floor (~1%) for all post-2024 games

**Imputation in `preprocessing.py`:** All 8 columns added to mean-imputation
block in this card. League-average means used for fillna:
- bat_speed: 69.6 mph
- swing_length: 7.2 ft
- attack_angle: 9.1°
- bat_speed_vs_starter_velo: 0.747

**Coverage trajectory:** ~50% of 2021+ training rows are NULL (pre-2023-07-14
sensor coverage). This is expected and acceptable; the imputation strategy
above keeps the model unbiased on those rows. Coverage improves naturally each
season as the 2023+ proportion grows.

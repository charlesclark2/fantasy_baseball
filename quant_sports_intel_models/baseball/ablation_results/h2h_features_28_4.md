# H2H Features (Story 28.4) — Travel/Fatigue + Interaction Terms

**Goal:** Add H2H-specific features and retrain, targeting credible-2026 Brier ≤ 0.195 (the 0.18–0.20 sharp-market band).

- Games: **11767**, home_win base rate 0.5311.
- Augmented features added: `home_travel_distance_miles, home_tz_delta_hours, home_is_3rd_consecutive_road_game, home_is_getaway_day, away_travel_distance_miles, away_tz_delta_hours, away_is_3rd_consecutive_road_game, away_is_getaway_day, home_starter_supp_X_away_offense, away_starter_supp_X_home_offense, run_diff_sigma`

## AC1 — Feature coverage (≥95% non-null required)

| feature | null rate | pass |
|---|---|---|
| `home_travel_distance_miles` | 0.0009 | ✅ |
| `home_tz_delta_hours` | 0.0000 | ✅ |
| `home_is_3rd_consecutive_road_game` | 0.0000 | ✅ |
| `home_is_getaway_day` | 0.0000 | ✅ |
| `away_travel_distance_miles` | 0.0009 | ✅ |
| `away_tz_delta_hours` | 0.0000 | ✅ |
| `away_is_3rd_consecutive_road_game` | 0.0000 | ✅ |
| `away_is_getaway_day` | 0.0000 | ✅ |
| `home_starter_supp_X_away_offense` | 0.0000 | ✅ |
| `away_starter_supp_X_home_offense` | 0.0000 | ✅ |
| `run_diff_sigma` | 0.0000 | ✅ |

**Coverage gate:** ✅ PASS

## AC1 — Orthogonality of travel features (|corr| < 0.70 with any signal column)

| feature | max |corr| vs signals | orthogonal |
|---|---|---|
| `home_travel_distance_miles` | 0.0334 | ✅ |
| `home_tz_delta_hours` | 0.0168 | ✅ |
| `home_is_3rd_consecutive_road_game` | 0.0000 | ✅ |
| `home_is_getaway_day` | 0.0253 | ✅ |
| `away_travel_distance_miles` | 0.0410 | ✅ |
| `away_tz_delta_hours` | 0.0199 | ✅ |
| `away_is_3rd_consecutive_road_game` | 0.0225 | ✅ |
| `away_is_getaway_day` | 0.0246 | ✅ |
| `home_starter_supp_X_away_offense` | 0.7995 | ❌ |
| `away_starter_supp_X_home_offense` | 0.8074 | ❌ |
| `run_diff_sigma` | 0.7097 | ❌ |

## Per-season head-to-head (identical market-covered games)

| season | n cov | model Brier | market Brier | Δ (mkt−mdl) | market quality | beats mkt |
|---|---|---|---|---|---|---|
| 2023 | 1601 | 0.1868 | 0.2442 | +0.0574 | ⚠️ degraded | — |
| 2024 | 1629 | 0.1866 | 0.2406 | +0.0541 | ⚠️ degraded | — |
| 2025 | 1663 | 0.1843 | 0.2434 | +0.0591 | ⚠️ degraded | — |
| 2026 | 733 | 0.2230 | 0.1887 | -0.0343 | credible | ❌ |
| POOLED | 5626 | 0.1907 | 0.2357 | +0.0450 | mixed | — |

> Degraded seasons (excluded from verdict): [2023, 2024, 2025] (market Brier > 0.235).

## AC2 — Confirmation gate

| gate | target | actual (2026) | result |
|---|---|---|---|
| credible-2026 Brier | ≤ 0.195 | 0.2230 | ❌ GATE NOT MET |

**❌ GATE NOT MET** — residual gap: 0.2230 − 0.195 = +0.0280. Feature augmentation does not close the market gap by itself. Route to Story 28.5 (Hierarchical Bradley-Terry).


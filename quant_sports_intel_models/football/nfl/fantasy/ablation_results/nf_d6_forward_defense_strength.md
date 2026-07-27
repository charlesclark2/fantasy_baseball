# NF-D6 — Forward defense-strength projection (roster-adjusted; the SOS baseline)

**Generated:** 2026-07-27T05:28:28.720672+00:00 · **walk-forward seasons:** 2016–2024 · opponent-adjusted mixed-model strength (`hierarchical.fit`), pass-D + rush-D separately. Edge-independent, `best_alpha=0`.

## Verdict — SHIP — opponent-adjusted + EB-shrunk strength (pooled ρ 0.250, ties raw); churn POINT-shrink adds no walk-forward lift ⇒ OFF (NF-D gate). Forward uncertainty = a calibrated season-to-season VOLATILITY floor 0.5 (1-sd coverage ≈0.69 vs the too-narrow measurement-only 0.63); churn does NOT predict forward surprise (ρ≈-0.041) ⇒ churn-specific widen OFF. Roster-churn / returning shares ship as diagnostics.

> The gate (a projection, like NF-D7): the shipped config must best predict next-year strength on the walk-forward metric, and the churn-widened uncertainty must be calibrated + earned (churn predicts forward surprise). Not `best_alpha`/PBO.

## 1. Walk-forward bake-off — Spearman(projected strength, realized next-year strength)

Realized target = that season's OPPONENT-ADJUSTED strength z (the de-noised truth); `_raw` = vs realized unadjusted EPA-allowed z. Pooled over all (season, team) within a unit.

| config | opp-adj | churn k | pass ρ | rush ρ | pooled ρ | pass ρ(raw) | rush ρ(raw) |
|--------|---------|---------|--------|--------|----------|-------------|-------------|
| raw | · | 0.0 | 0.289 | 0.227 | **0.258** | 0.265 | 0.228 |
| oppadj | ✓ | 0.0 | 0.281 | 0.219 | **0.250** | 0.249 | 0.219 |
| oppadj_churn_k0.15 | ✓ | 0.15 | 0.281 | 0.218 | **0.249** | 0.249 | 0.218 |
| oppadj_churn_k0.3 | ✓ | 0.3 | 0.280 | 0.217 | **0.248** | 0.248 | 0.216 |
| oppadj_churn_k0.5 | ✓ | 0.5 | 0.279 | 0.213 | **0.246** | 0.247 | 0.213 |

## 2. Uncertainty validation — the churn hypothesis + interval calibration

**(a) Does churn predict forward surprise?** ρ(churn, |forward error|) = **-0.041** (n=560). Mean |forward error|: low-churn tercile **1.006** vs high-churn **0.936**. ⇒ NULL — roster churn does NOT predict a larger forward surprise for defense (continuity is entangled with having been good, and good units regress unpredictably). The churn-SPECIFIC widen is NOT shipped.

**(b) Interval calibration.** RMS forward change ≈ **1.223** z-units — far larger than the measurement sd (~0.3), so the honest forward interval needs a season-to-season VOLATILITY floor. 1-sd coverage by floor:

| forward-noise floor | 1-sd coverage |
|---------------------|---------------|
| 0.0 | 0.632 |
| 0.5 | 0.689 ← selected |
| 0.75 | 0.741 |
| 0.9 | 0.770 |
| 1.0 | 0.782 |
| 1.2 | 0.830 |

Nominal 1-sd coverage = 0.68; selected floor = **0.5** (measurement-only floor 0.0 under-covers at 0.632).

## 3. Face-validity — 2024 most-reshaped defenses (SHIP config)

### PASS-D — biggest roster turnover (highest churn = the least-certain projections; the returning shares + losses/adds ship as diagnostics)

| team | returning | churn | prior z | fwd strength | fwd sd | key losses | key adds |
|------|-----------|-------|---------|--------------|--------|------------|----------|
| TEN | 0.301 | 0.699 | -1.128 | -1.128 | 1.086 | Sean Murphy-Bunting, Denico Autry, Elijah Molden | Quandre Diggs, L'Jarius Sneed, Chidobe Awuzie |
| WAS | 0.313 | 0.687 | -2.143 | -2.143 | 1.084 | Kamren Curl, Kendall Fuller, Casey Toohill | Michael Davis, Marshon Lattimore, Clelin Ferrell |
| CAR | 0.324 | 0.676 | 0.306 | 0.306 | 1.131 | Donte Jackson, Vonn Bell, Troy Hill | Jordan Fuller, Akayleb Evans, Rudy Ford |
| DEN | 0.376 | 0.624 | -0.931 | -0.931 | 1.090 | Justin Simmons, Fabian Moreau, Ja'Quan McMillian | Levi Wallace, John Franklin-Myers, Brandon Jones |
| JAX | 0.409 | 0.591 | 0.694 | 0.694 | 1.077 | Rayshawn Jenkins, Darious Williams, Tre Herndon | Darnell Savage Jr., Ronald Darby, Matthew Jackson |

### RUSH-D — biggest roster turnover (highest churn = the least-certain projections; the returning shares + losses/adds ship as diagnostics)

| team | returning | churn | prior z | fwd strength | fwd sd | key losses | key adds |
|------|-----------|-------|---------|--------------|--------|------------|----------|
| WAS | 0.290 | 0.710 | -0.148 | -0.148 | 1.696 | Cody Barton, Jamin Davis, Casey Toohill | Bobby Wagner, Frankie Luvu, Clelin Ferrell |
| CAR | 0.359 | 0.641 | -2.524 | -2.524 | 1.692 | Frankie Luvu, Brian Burns, Yetur Gross-Matos | D.J. Wonnum, Josey Jewell, Jadeveon Clowney |
| LAC | 0.432 | 0.568 | -0.071 | -0.071 | 1.708 | Kenneth Murray, Eric Kendricks, Austin Johnson | Bud Dupree, Denzel Perryman, Teair Tart |
| MIN | 0.437 | 0.563 | 0.052 | 0.052 | 1.717 | Danielle Hunter, D.J. Wonnum, Jordan Hicks | Andrew Van Ginkel, Jihad Ward, Blake Cashman |
| DEN | 0.438 | 0.562 | -0.421 | -0.421 | 1.703 | Alex Singleton, Josey Jewell, Jonathan Harris | Cody Barton, Zach Cunningham, John Franklin-Myers |

## Disposition

- **Ship config:** `oppadj` — opponent-adjusted mixed-model strength, churn point-shrink k=0.0, forward-volatility floor=0.5, churn-specific widen k=0.0.
- Delivered as `defense_source.load_forward_defense(season)` → per-team `pass_def_strength` / `rush_def_strength` (+ `_sd`), landed to `nfl/fantasy/defense/forward_defense_strength` (season-partitioned Delta). NF1.2's SOS joins it the same way NF1.1 joins the xFP set.
- Leakage-safe: opponent-adjusted efficiency + league fit read ≤ prior season; the roster-churn layer uses the preseason-known projection-season roster (the NF-D1/NF-D2 posture). Edge-independent, `best_alpha=0`.


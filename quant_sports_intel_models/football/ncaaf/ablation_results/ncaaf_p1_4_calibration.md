# NCAAF-P1.4 — served NCAAF joint game distribution (calibration)

_Fit 2026-07-23 · learner `ridge` · contract `strength_only` · form `strength_posterior` · 6,024 OOS games_

## Served contract

- form **strength_posterior** · σ_margin `16.086901549597975` · σ_total `16.746709708076466` · ρ `0.05603365986298882` · dof `30.0`

## Distribution gate (pooled OOS)

| dist | calib_80 | PIT max-decile-dev | PIT-flat |
|---|---|---|---|
| margin | 0.800 | 0.0080 | ✅ |
| total | 0.802 | 0.0218 | ❌ |

**calib floor:** PASS ✅ · **PIT-flat:** FAIL ❌ · **H2H Brier** 0.1814

## Early-season / cold-start validation (season_order_week ≤ 3, n=1051)

Week 1–3 is a priors-heavy regime (in-season efficiency NULL) whose quality the season-averaged aggregate HIDES; validated separately as a FLOOR. Season-forward CV predicts a week-1 game from PRIOR-SEASON + PRE-SEASON data only (the E13.7 cold-start analog), confirmed below.

- calib_80 — margin **0.792** / total **0.822** · early floor **PASS ✅** · PIT-flat margin True
- week-1 80% interval width — margin **43.1** vs late-season 40.8 (×1.056) — honestly WIDER when both teams have 0 in-season games
- cold-start no-peek: 100% of week-1 eval games carry NULL in-season features **✅ no current-season leakage**

## Downstream season-simulation interface (P1.5 futures — do NOT collapse the output)

`ncaaf_game_predictor.sample_matchup(...)` exposes the joint predictive for P1.5's NC/conference-title Monte-Carlo. ⭐ The width DECOMPOSES: `σ_g² = σ₀² + k²·(home_sd² + away_sd²)` — irreducible game noise + the strength posterior. A season sim draws each team's strength ONCE per simulated season (from the P1.2 `ncaaf_team_strength_week` posterior) and reuses it across the schedule, so it must call `sample_matchup(..., fixed_strength=True)` (σ₀ only) to avoid DOUBLE-COUNTING the strength uncertainty. The served params carry σ₀ and k separately for exactly this.

## vs-close CLV (2020–2025 historical)

- ATS model-side hit **0.496** (n=4110, placebo 0.497, breakeven 0.5238)
- O/U model-side hit **0.523** (n=4129)

historical vs-close hit rates; > 0.5238 clears the -110 vig. best_alpha=0 until this beats breakeven AND the placebo under deflation, confirmed by a forward in-season CLV window (post-kickoff, P0.6b-fed).

## Honest framing

Market-BLIND joint distribution = product value (calibrated 3-market probabilities), NOT an edge claim (`best_alpha = 0`). A hit rate near 50% is the expected null; a real edge needs > breakeven AND > placebo under deflation, confirmed in-season by forward CLV (which cannot exist pre-season).

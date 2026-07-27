# NF1 — the joint learned re-weighting + the matchup-aware weekly leg (market-blind)

**Model:** `nfl_fantasy_nf1_v1` · **status:** bake-off + weekly ablation RUN on the real lake (2026-07-26); the winner is selected; the final `build --s3` + the full 6-season NF-D3 grade are the operator's remaining laptop runs (commands in the handoff). · **edge-independent** (projection product; no PBO/DSR/CLV).

> ⚖️ **What NF1 is.** MVP-1 (`season_projection.py`) layers each NF-D signal as a fixed HEURISTIC scalar in sequence. **NF1 does the JOINT LEARNED re-weighting** of that same signal set (the operator's "consolidation home"), plus a matchup-aware weekly leg. Pure logic in `nf1_model.py`; DuckDB reads / walk-forward bake-off / calibration / S3 landing / NF-D3 grade in `run_nf1.py`.

## 0. Two scope calls (operator, 2026-07-26)
- **FULL matchup-aware weekly** — a real per-player-week model = season per-game baseline × defense-vs-position × Vegas implied-team-points × home, Gamma posterior-predictive; **ablated per §0.5**.
- **MARKET-BLIND** — NO ADP/ECR features (orthogonal NF-D signals only); ADP/ECR stay the NF-D3 benchmark. A market-blind NF1 cannot close the QB/RB gap vs consensus by following the market (that gap IS the market signal) — its job is to extract more ordering from the orthogonal set than MVP-1's fixed heuristic product, and hold the honest-analytics identity (the edge is the disagreements).

## 1. The §0.5 season bake-off (market-blind) — RESULT
Walk-forward CV by season (fit target<Y, predict Y), base seasons 2017–2024, 7 scored targets 2019–2025 (pool 2,995), each learner Optuna-tuned (40 trials) on held-out within-position ρ, oracle-floor-checked (PASS).

| learner | pooled ρ | **QB** | RB | WR | TE | overfit gap |
|---------|---------:|-------:|---:|---:|---:|------------:|
| heuristic_null (MVP-1) | 0.718 | 0.648 | 0.734 | 0.750 | 0.740 | — |
| ridge | 0.727 | 0.632 ↓ | 0.746 | 0.777 | 0.754 | +0.005 |
| elasticnet | 0.724 | 0.619 ↓ | 0.746 | 0.776 | 0.757 | +0.011 |
| **gbm (WINNER)** | **0.732** | **0.661 ↑** | 0.743 | 0.776 | 0.747 | +0.071 |

**Winner = GBM.** All learned candidates beat the MVP-1 null on pooled ρ (WR is the big shared win, 0.750→~0.777), but **the discriminator is QB — the operator's flagged-weakest position.** The two LINEAR blends *regress* QB below the null (0.632/0.619 vs 0.648); **GBM is the only candidate that improves QB (0.661)** while topping pooled ρ. GBM's overfit gap (0.071, train 0.802 vs held-out 0.732) is the small-data signature — a documented caution, but selection is on the honest walk-forward held-out where GBM leads. **Feature ablation (on GBM):** every group contributes (all-negative drop deltas); **`age` is the single biggest add (−0.010)** — validating the one feature NF1 adds over MVP-1. `hp = {n_estimators:100, num_leaves:20, learning_rate:0.0161, min_child_samples:19}`.

## 2. Applying the learned model — ORDERING, not level (a fixed design bug)
⚠️ **First build attempt was corrupted by a design error, now fixed.** The learner trains on `real_fp_ppr` of players who actually played ≥6 games — a SURVIVORSHIP-selected level systematically ABOVE MVP-1's risk-adjusted projection. Rescaling MVP-1's raw line directly to that learned LEVEL saturated the clamp (`nf1_scale` mean 1.5, mass pinned at the 1.75 ceiling) and **scrambled the very ordering the bake-off picked** (a rookie QB floated to #1 overall; Josh Allen scaled to 0.75).
- **Fix (the E2.1-r discrimination-vs-pricing lesson):** the bake-off validated the learner's ORDERING, not its LEVEL. `apply_learned_ordering` reorders each position by the learned score and hands it that position's own MVP-1 point MULTISET (a within-position quantile remap — the `blend_adp_prior` mechanism) → the shipped within-position rank == the validated bake-off rank EXACTLY, while the point scale + the calibrated interval stay MVP-1's (calibrated). Then the raw line is rescaled to its assigned level (raw-line contract intact for NF-C1).
- **Verified after the fix:** `nf1_scale` mean **1.03** (0.2% clamped, was ~1.5 saturated); top-8 = veteran QBs (Lamar/Herbert/Burrow/Hurts/Allen — the normal raw-PPR-pre-VOR shape; VOR/NF-C1 drops QBs for standard leagues); the rookie-QB-#1 symptom is gone (Mendoza back to ~QB9 — the KNOWN, deferred rookie-model over-valuation, NF1 = veteran re-weighting only). Season interval CALIBRATED: κ=1.725 → **calib_80 = 0.805** (floor met), PIT max-decile-dev 0.20 (`uncertainty_type=calibrated`).

## 3. The matchup-aware weekly leg — §0.5 ablation = NULL → ship flat
60 weeks × 2021–2024, scored on held-out weekly within-position ρ vs realized:

| arm | weekly ρ | Δ vs flat |
|-----|---------:|----------:|
| flat_baseline | 0.500 | 0.000 |
| +dvp | 0.497 | −0.003 |
| +env | 0.493 | −0.007 |
| +home | 0.501 | +0.001 |
| full_matchup | 0.487 | −0.013 |

**The scalar matchup tilts do NOT lift weekly ordering (all Δ ≤ 0, within noise) → per the slice-gate discipline they are DROPPED** (the NGS slice-2 precedent). The served weekly ships the FLAT calibrated season-per-game-per-week baseline; DVP / implied-points are still CARRIED as matchup CONTEXT for the UI, not applied to the point. The weekly INTERVAL is a first-order Gamma approximation (PIT ~0.23; weekly points are zero-inflated + heavy-tailed) — FLAGGED for recalibration before weekly pricing (E13.6 pattern). **Future lever:** a richer STAT-level opponent model (a defense that suppresses passing but not rushing; EPA-based) rather than a single scalar fp tilt — the scalar tilt is the honest null here.

## 4. NF-D3 grade vs consensus (market-blind, as designed)
On the FIXED board (2-season 2023–2024 spot-check; the operator's full 6-season grade is the ship number): vs **ADP** Δρ **−0.011** (QB **−0.002** ≈ TIED the market on ADP-covered QBs — vs the corrupted board's −0.225) and we **WIN the ADP fades (0.435 vs 0.288)**; vs ECR/ESPN/Sleeper still behind on pooled (−0.058 / −0.079 / −0.087). **As designed:** a market-blind NF1 does not close the full top-tier gap (that gap is the market signal we excluded), but it is now COMPETITIVE at QB vs ADP and wins the fades. **Honest-claim scope UNCHANGED:** never "we beat consensus"; the airtight claim stays narrow (high-conviction fades + WR/QB-vs-ADP competitiveness).

## 5. Files
- `nf1_model.py` (NEW, pure) — learners + registry, `apply_learned_ordering` (the remap) + `apply_learned_level`, calibration + E2.1-r hygiene (`randomized_pit`, `pit_max_decile_deviation`, `calibrate_dispersion` floor, `oracle_ordering_is_the_ceiling`), weekly matchup (`defense_vs_position_factor`, `environment_factor`, `project_week`, Gamma predictive).
- `run_nf1.py` (NEW, CLI/IO) — feature assembly (reuses the MVP-1 pure helpers → features never drift), `bakeoff` / `weekly-bakeoff` / `build` / `grade` modes, S3 landing to its OWN prefix `nfl/fantasy/derived/nf1_season_projections/` (does NOT overwrite MVP-1).
- `betting_ml/tests/test_nf1_model.py` (NEW, 20 fast-gate tests).
- `nf1_season_bakeoff.{md,json}` (the §0.5 result), `nf1_weekly_bakeoff.{md,json}` (the weekly null).

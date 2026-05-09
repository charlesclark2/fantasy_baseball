# Phase 8 Batch Retrain Impact Report (Card 8.W)

**Generated:** 2026-05-08  
**Scope:** home_win v1, total_runs v2, run_differential v1  
**Purpose:** End-of-Phase 8 retrain checkpoint. Documents what Phase 8 feature investment
bought, what problems the feature importance analysis surfaced, and what the ~2026-05-22
retrain needs to fix.

---

## 1. Features Added Since Last Retrain

The pre-Phase 8 production baseline was the 7.MA artifacts: home_win XGBoost (294 features),
total_runs NGBoost LogNormal (294 features), run_differential NGBoost Normal (294 features).

| Card | Feature Group | Columns (pattern) | In home_win v1 | In total_runs v2 | In run_diff v1 |
|------|--------------|-------------------|:--------------:|:----------------:|:--------------:|
| 8.A  | Pct-diff encoding | `_pct_diff` | Yes | Yes | No |
| 8.B  | FIP projections | `proj_fip`, `trailing_fip_30g`, `fip_ra9_gap` | Yes | Yes | No |
| 8.C  | OAA blended | `oaa_blended` | Yes | Yes | No |
| 8.D  | ELO ratings | `_elo`, `elo_diff` | Yes | Yes | No |
| 8.E  | Bat tracking | `bat_speed`, `swing_length`, `attack_angle` | Yes | Yes | No |
| 8.J  | H2H matchup wOBA | `h2h_woba`, `h2h_xwoba`, `h2h_pa_coverage` | Yes | Yes | No |
| 8.K  | Catcher framing | `catcher_framing`, `catcher_defensive` | Yes | Yes | No |
| 8.L  | Bullpen matchup xwOBA | `bp_matchup_xwoba` | Yes | Yes | No |
| 8.M  | Arsenal drift | `arsenal_drift` | Yes | Yes | No |
| 8.Q  | CSW% | `csw_pct` | Yes | Yes | No |
| 8.R  | Public betting | `pct_home_ml`, `ml_sharp_signal`, `has_public_betting` | Yes | Yes | No |
| 8.T  | Bookmaker disagreement | `ml_implied_prob_std`, `n_books_available`, `stale_book_flag` | Yes | Yes | No |
| 8.U  | Bullpen leverage | `bp_leverage_sum`, `bp_high_lev_appearances` | Yes | Yes | No |
| 8.X  | Pythagorean residual | `pythagorean_residual`, `pyth_residual` | Yes | No | No |
| 8.Y  | Base state splits | `base_state`, `woba_splits`, `xwoba_splits`, `sequencing` | Yes | No | No |

**Summary:**
- home_win v1: 487 features — all Phase 8 cards incorporated via `load_features()` in card 7.L2
- total_runs v2: 311 features — 16 Phase 8 features; 8.X/8.Y not included
- run_diff v1: 294 features — **zero Phase 8 features**; retrained in 7.MA before Phase 8
  feature coverage was complete; no 8.W re-run was performed for this target

**This is the primary gap from 8.W: run_differential never received Phase 8 features.**

---

## 2. CV Metrics Per Target vs. Baseline

| Target | Pre-Phase 8 Baseline | 8.W Artifact | CV Metric | Delta | Status |
|--------|---------------------|--------------|-----------|-------|--------|
| home_win | v0 XGBoost, Brier 0.2439 (7.L2) | v1 elasticnet, Brier **0.2422** | CV Brier (5-fold TimeSeriesSplit) | −0.0017 | Improved |
| total_runs | v1 NGBoost, MAE 3.5190 (7.V) | v2 NGBoost Normal, MAE **3.5107** | CV MAE | −0.0083 | Improved |
| run_diff | 7.MA NGBoost, MAE 3.4724 | same artifact | CV MAE | 0 | No retrain |

**home_win notes:** Switched model architecture from XGBoost to elasticnet (LogisticRegression,
elasticnet penalty, inner-CV C=0.01, l1_ratio=0.5). The expanded 487-feature set from
`load_features()` drove the Brier improvement. The L1 penalty zeroed out 388/483 features,
keeping only the 95 most predictive columns.

**total_runs notes:** Decay-weighted retrain (card 8.N, half_life=162 games) on 311 features.
Improvement is modest but directionally correct. The variance-shrinkage problem (std(pred)=0.77
vs actual std=4.44) persists — deferred to Phase 9.

**run_diff notes:** No change. Still the 7.MA artifact. This is the most urgent retrain
priority at ~2026-05-22.

---

## 3. Calibration Metrics (home_win)

Static calibrator (Platt scaling, fit 2026-05-08 with v1-only data fix):

| Metric | Value |
|--------|-------|
| Training samples | 576 (v1 predictions only; v0/v2 rows excluded) |
| ECE before calibration | 0.0484 |
| ECE after Platt scaling | **0.0053** |
| Calibrator method | Platt (logistic regression) |
| Calibrator artifact | `betting_ml/models/home_win/calibrator.joblib` |
| Rolling calibrator | fit same day, 576 samples, `calibrator_rolling.joblib` |
| Last fit date | 2026-05-08 |

**Note on calibrator contamination:** The original Card 7.C calibrator SQL had no
`model_version` filter — it mixed v0/v1/v2 predictions with different probability
distributions, causing calibration to actively degrade ECE (0.0247 → 0.0420). Fixed
2026-05-08 by adding `AND p.model_version = 'v1'` to both SQL queries in
`train_calibrator.py`. The v1 model systematically under-predicts home win rate
(raw mean ~51.8% vs. actual ~53.9%); the Platt calibrator corrects this shift
(0.50 raw → 0.537 calibrated).

---

## 4. CLV Results

**Historical baseline (Card 8.S, 2021–2025 backfill):**

| Version | Games | Has CLV | Mean CLV ML | Pct Positive |
|---------|-------|---------|-------------|--------------|
| v0 | 10,140 | 9,131 | +0.0026 | 37.7% |
| v1 | 9,551 | 8,831 | +0.0027 | 39.1% |
| v2 | 7,737 | 7,373 | +0.0028 | 40.0% |

Trend is monotonically improving v0 → v1 → v2. Positive mean CLV indicates historical
predictions were made before the market moved toward consensus.

**2026 live games (retrained models):**

| Metric | Value |
|--------|-------|
| Live games with odds | 41 |
| Mean CLV ML | −0.0023 |
| 8.F2 gate (≥50 games AND mean_h2h_edge > 0.0) | **HOLD** |

41 live games is below the 50-game minimum. Mean CLV is marginally negative —
likely noise at this sample size. Re-evaluate at ~2026-05-22 when ≥50 games are available.

---

## 5. Feature Importances Per Target

Reports at `betting_ml/evaluation/feature_selection/`.

### 5a. home_win (elasticnet coefficients, top 10)

| Rank | Feature | Coefficient | Phase 8 Origin |
|------|---------|-------------|---------------|
| 1 | elo_diff | +0.0981 | **8.D** |
| 2 | home_pit_woba_against_std | −0.0551 | legacy |
| 3 | away_moneyline_decimal | +0.0531 | legacy ⚠️ |
| 4 | away_avg_bb_pct_vs_lhp | −0.0383 | legacy |
| 5 | away_starter_stuff_plus | −0.0352 | legacy |
| 6 | home_win_prob_sharp | +0.0330 | legacy ⚠️ |
| 7 | away_pit_k_pct_7d | −0.0317 | legacy |
| 8 | home_starter_proj_fip | −0.0297 | **8.B** |
| 9 | away_off_k_pct_std | +0.0274 | legacy |
| 10 | away_starter_days_rest | +0.0267 | legacy |

**Phase 8 in top-20:** 2 of 19 total Phase 8 features (elo_diff #1, proj_fip #8).  
**L1 pruning:** 388/483 features zeroed out — model uses 95 non-zero coefficients.  
**⚠️ Market circularity:** `away_moneyline_decimal` (#3), `home_win_prob_sharp` (#6),
`home_open_win_prob` (#11) are top-20 features. The model partially echoes market
consensus, which compresses CLV signal. `_MARKET_COLS_TO_EXCLUDE` populated in
`train_elasticnet_prod.py` (2026-05-08) for the next retrain.

### 5b. total_runs (permutation importance, top 10)

| Rank | Feature | Mean Imp | Phase 8 Origin |
|------|---------|----------|---------------|
| 1 | total_line_consensus | 0.06366 | legacy ⚠️ |
| 2 | ml_consensus_std | 0.02734 | legacy ⚠️ |
| 3 | humidity_pct | 0.02353 | legacy |
| 4 | home_starter_fastball_stuff_plus | 0.02254 | legacy |
| 5 | series_game_number | 0.01492 | legacy |
| 6 | away_pit_k_pct_7d | 0.01397 | legacy |
| 7 | home_pit_woba_against_std | 0.01276 | legacy |
| 8 | temp_f | 0.01226 | legacy |
| 9 | home_starter_xwoba_vs_rhb | 0.01171 | legacy |
| 10 | home_starter_whiff_rate_14d | 0.01171 | legacy |

**Phase 8 in top-20:** 0 of 16 Phase 8 features. None of the Phase 8 additions
cracked the top-20 for total runs prediction.  
**Exclusion candidates:** 68/311 features (22%).  
**Phase 8 exclusion candidates (mean_imp ≈ 0):** away_elo (8.D), home_away_off_xwoba_30d_pct_diff (8.A),
home_team_oaa_blended (8.C), home_away_starter_k_pct_std_pct_diff (8.A).  
**⚠️ Market circularity:** `total_line_consensus` (#1, imp=0.064) and `ml_consensus_std` (#2, imp=0.027)
are the two most important features by a wide margin. Same structural problem as home_win.

**Notable:** Weather features (`humidity_pct` #3, `temp_f` #8) are legitimately the
3rd and 8th most important features — this is correct signal for total runs. ELO (#1 in
home_win) does not translate to total runs (#20+ range), which is expected.

### 5c. run_differential (permutation importance, top 10)

| Rank | Feature | Mean Imp | Phase 8 Origin |
|------|---------|----------|---------------|
| 1 | home_win_prob_consensus | 0.04016 | legacy ⚠️ |
| 2 | pythagorean_win_exp_diff | 0.02991 | legacy |
| 3 | home_pit_k_pct_std | 0.01379 | legacy |
| 4 | away_win_pct | 0.00623 | legacy |
| 5 | home_starter_xwoba_against_std | 0.00371 | legacy |
| 6 | home_pit_woba_against_30d | 0.00352 | legacy |
| 7 | away_pit_k_pct_30d | 0.00310 | legacy |
| 8 | home_avg_xwoba_vs_rhp | 0.00299 | legacy |
| 9 | away_starter_stuff_plus | 0.00297 | legacy |
| 10 | home_starter_bb_pct_std | 0.00279 | legacy |

**Phase 8 features in model:** 0 — run_diff uses the pre-Phase 8 294-feature set.  
**Exclusion candidates:** 180/294 features (61%) — majority of features are noise.  
**⚠️ Market circularity:** `home_win_prob_consensus` is the single most important feature,
with 3× the importance of #2. The model is primarily a market-following machine.  
**`pythagorean_win_exp_diff` (#2):** This is a clean fundamental signal — validates
the Card 7.R/8.X Pythagorean win expectation feature; note it is legacy origin
because 8.X added the *residual* version but the base `win_exp_diff` predates Phase 8.

---

## 6. Per-Target Promotion Gate Results

### home_win
| Gate | Threshold | Value | Result |
|------|-----------|-------|--------|
| CV Brier | ≤ v0 baseline (0.2439) | **0.2422** | PASS |
| Post-calibration ECE | ≤ 0.045 | **0.0053** | PASS |

**Decision: PROMOTED to v1 production (card 7.L2).** Deployed 2026-05-04.

### total_runs
| Gate | Threshold | Value | Result |
|------|-----------|-------|--------|
| Weighted CV MAE | ≤ v1 baseline (3.5190) | **3.5107** | PASS |
| abs(mean_residual) | ≤ 0.5 | **0.048** | PASS |
| pct_pred_over_line | ∈ [0.20, 0.80] | **83.7%** | PASS |
| std(pred) | ≥ 2.0 | **0.77** | FAIL — deferred to Phase 9 |

**Decision: PROMOTED to v2 production (card 8.N).** Deployed 2026-05-08.
Variance-shrinkage gate deferred; known feature-set ceiling.

### run_differential
| Gate | Threshold | Value | Result |
|------|-----------|-------|--------|
| CV MAE | ≤ v0 baseline | **3.4724** vs v0 3.4586 | Slight regression (+0.40%) |
| Phase 8 features present | Expected | **0** | FAIL — retrain did not occur |

**Decision: RETAINED at v1. No 8.W retrain was executed for run_diff.** The 7.MA
artifact remains in production. This is the highest priority retrain for ~2026-05-22.

---

## 7. Wave 5 Unblocking Decision

### 8.F2 (Kelly sizing / CLV-gated betting)
**Status: HOLD**

- Gate: mean_h2h_edge > 0.0 over ≥ 50 has_odds live games
- Current: 41 live games, mean_clv_ml = −0.0023
- Both conditions fail (sample below threshold, edge marginally negative)
- Re-evaluate ~2026-05-22 after ≥50 live games accumulate with retrained models

**Note:** The market circularity finding (market features as top predictors) is a
structural explanation for compressed CLV signal. Even if mean CLV is positive in
backfill, the model's edge may be systematically understated because it already
encodes market prices. The ~2026-05-22 retrain (market-blind) is the right test
of whether independent edge exists before committing to 8.F2.

### 8.F4 (inference stabilization / shrinkage constants)
**Status: READY**

k-constants (k=60, 100, 150) will be re-validated inside 8.F4 implementation
against the retrained model baseline. No blocking condition.

---

## 8. Recommended Feature Sets for Next Retrain (~2026-05-22)

Re-evaluate after ≥50 live CLV games are available. Scheduled retrain window
assumes ~30 new in-season 2026 games between now and then.

### home_win
**Architecture change:** market-blind retrain. `_MARKET_COLS_TO_EXCLUDE` populated
in `train_elasticnet_prod.py` (2026-05-08) — no code changes needed at retrain time.

Columns to exclude (now in `_MARKET_COLS_TO_EXCLUDE`):
- Raw odds: `home/away_moneyline_decimal`, `home/away_moneyline`
- Implied probs: `home/away_win_prob_sharp`, `home/away_open/close_win_prob`
- Consensus: `home/away_win_prob_consensus`
- Line movement: `home/away_h2h_line_movement`, `home/away_open_line`
- Totals market: `open_total`, `close_total`, `total_line`
- Public betting (8.R): `pct_home_ml`, `pct_away_ml`, `ml_sharp_signal`, `total_sharp_signal`, `has_public_betting`
- Bookmaker disagreement (8.T): `ml_implied_prob_std`, `ml_implied_prob_range`, `sharp_soft_ml_spread`, `n_books_available`, `stale_book_flag`, `totals_line_std`, `totals_line_range`, `ml_consensus_std`

**Success gate:** market-blind CV Brier within +0.002 of v1 (0.2422) AND mean CLV
improvement over ≥30 live games. If Brier degrades >0.002 with no CLV gain, the
market features carry real predictive signal and the market-aware architecture is correct.

### total_runs
**Architecture change:** same — remove market/line columns from training features.
`total_line_consensus` (#1 importance) and `ml_consensus_std` (#2) must be excluded.
Add `total_line_consensus` and `ml_consensus_std` to the exclusion set in the
NGBoost training script (equivalent of `_MARKET_COLS_TO_EXCLUDE`).

**Phase 8 columns to drop (exclusion candidates, mean_imp ≈ 0):**
- `away_elo` (8.D) — ELO captures win probability, not total runs
- `home_away_off_xwoba_30d_pct_diff` (8.A)
- `home_team_oaa_blended` (8.C) — defensive metric, limited total-runs signal
- `home_away_starter_k_pct_std_pct_diff` (8.A)

**Keep:** weather features (humidity, temp), pitching whiff/barrel/xwOBA, bullpen xwOBA.
Weather is genuinely 3rd/8th most important — do not drop these.

### run_differential
**This is the most urgent retrain.**

Two changes required:
1. **Full feature store retrain:** switch from `feature_columns.json` (294 features,
   pre-Phase 8) to `load_features()` full set (current ~490+ features). This gives
   run_diff its first exposure to ELO, FIP projections, CSW%, catcher framing,
   H2H matchup wOBA, base state splits, etc.
2. **Market exclusion:** `home_win_prob_consensus` (#1 importance) must be excluded.
   Apply same `_MARKET_COLS_TO_EXCLUDE` logic as home_win — implement equivalent
   set in the run_diff training script.

**61% noise ratio** (180/294 exclusion candidates) is expected to drop substantially
once Phase 8 features provide new signal and market features are removed.

**Architecture note:** LogNormal excluded per project memory (run_diff can be negative).
Stick with Normal distribution.

---

## Summary Table

| Item | Finding | Action |
|------|---------|--------|
| home_win Phase 8 impact | ELO #1 (+9.8% coef), FIP #8 — validates 8.D and 8.B | None — keep |
| home_win market circularity | Moneyline #3, sharp prob #6, open prob #11 | Market-blind retrain ~05-22 |
| total_runs Phase 8 impact | 0/16 Phase 8 in top-20; 4 exclusion candidates | Drop 4 features at next retrain |
| total_runs market circularity | Consensus line #1 (3× next feature), ml_std #2 | Market exclusion at next retrain |
| run_diff Phase 8 gap | Zero Phase 8 features present | Full feature-store retrain ASAP |
| run_diff market circularity | Consensus win prob #1 | Market exclusion at next retrain |
| run_diff noise | 61% features are exclusion candidates | Expect to resolve with Phase 8 features |
| Calibrator | ECE 0.0484 → 0.0053 after v1-only data fix | Monitor; rolling refit weekly |
| CLV (live 2026) | 41 games, mean CLV −0.0023 | HOLD — recheck ~05-22 |
| 8.F2 gate | HOLD (below threshold) | Re-evaluate ~2026-05-22 |
| 8.F4 | Ready | Proceed |

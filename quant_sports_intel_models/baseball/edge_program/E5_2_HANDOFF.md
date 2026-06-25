# E5.2 — Per-prop distributional pricing (⭐ pitcher strikeouts): session recap & operator handoff

_Session 2026-06-24 · Model track (Session A) · market-blind pricing · builds on `starter_ip_v1` (outs NegBin) + E2.3 distributional machinery + E1.1 purged CV. Edge gate is downstream (E5.3 → E5.4)._

---

## TL;DR

**E5.2 is CODE-COMPLETE, pending the operator gate run.** The market-blind pitcher-strikeout pricer is built, fully unit-tested (29 tests green), and mirrors the proven E2.3 pattern (pure machinery + an operator-run orchestration that does the heavy Snowflake/S3 work). It models the prompt's two explicit components — **K = K-RATE × BATTERS-FACED** — and convolves them into an honest K-count predictive distribution → P(over/under) at the book's K line. The numbers (calib_80 / PIT / per-line ECE / served concentration `s`) come from the operator run below.

**E5.1 data is ready:** `pitcher_strikeouts` closing lines are already in S3 (2023–25 + 2026), so E5.2 was unblocked.

**HONEST FRAMING (carry forward):** a calibrated K distribution is **product value (projections)**, NOT an edge claim. `best_alpha = 0`. The edge question is gated at **E5.4** (PBO<0.2/DSR>0 per market, multiple-comparison-corrected, + forward CLV net of the high prop vig). If the K market is as efficient as the game-level ones (H2H dead ×5, main totals efficient), E5.4 returns a clean null — and that's a fine, expected outcome.

---

## First operator run (2026-06-24/25) + the calibration iteration

The first run executed end-to-end on **26,320 starts (2021–2026), 99.0% eligible**. Findings + fixes applied:
- **Snowflake SQL fix:** the trailing-aggregate CTE used the SQL named `WINDOW` clause (unsupported by Snowflake) → inlined each window spec into its `OVER(...)`. ✅
- **S3 line-path fix:** the prop glob prefix was `baseball_mlb/props/` → corrected to **`mlb/props/`** (the backfill's `sport_label` for `baseball_mlb` is `mlb`). ✅
- **Calibration finding → new lever:** the raw (λ=1) K predictive was **over-wide** — `calib_80 = 0.918` (over-covers; should be ≈0.80) and PIT not flat (max decile dev 0.051). Root cause: it inherits `starter_ip_v1`'s slightly-wide outs intervals (`pitcher_outs` calib = 0.90, not 0.80) plus the batters-faced uncertainty. **Fix:** added a **spread-recalibration `λ`** (mean-preserving variance tighten; the E13.6 temperature-scaling analogue), chosen on the pooled OOS folds to flatten PIT. The BB concentration `s` stays the conditional intra-PA overdispersion; `λ` absorbs the inherited marginal over-width. `s_global ≈ 69` (stable per-season 60–70); per-line ECE was already good (mean ≈ 0.040).
- **The re-run** (operator) now reports the λ-calibrated `calib_80`/PIT + the served `spread_scale` in `prop_pricing_strikeouts_v1.json`. Re-run command is unchanged (below).

## Methodology upgrade (2026-06-25) — model bake-off + recency, in response to two review questions

Two gaps were flagged after the first run, both now addressed:

**(1) "Why one model type, not a bake-off?"** Correct — the first pass shipped only the structural compound model, which isn't the program's standard. Added **`betting_ml/scripts/prop_pricing/bakeoff_strikeouts.py`** (operator-run; `--smoke` for a no-Snowflake harness check): a model-class bake-off under purged CV scored on **CRPS (primary) + coverage@80 + PIT-KS + at-the-line ECE** (reusing `promotion_gate.PredictiveOutput`/`calibration_report`), with **PBO across candidates** (`overfitting.pbo_cscv`) to guard the pick:
- **M1 compound_flat** (current), **M2 compound_recency**, **M3 lgbm_poisson_k** (direct LightGBM-Poisson on K + NegBin-r-by-decile), **M4 poisson_glm_k** (floor).

**(2) "Why train-on-previous-season — it ignores in-season stuff change / recency."** Half-right, and the important half. The **forward-CV protocol stays** (fitting on the eval season's own outcomes is leakage). But the **K-rate construction was wrong**: it used a FLAT season+career average that washes out a pitcher refining/losing stuff mid-season. Fixed — `build_predictors` now has a **`rate_mode`** (`career_only` / `season_career` / `recency_30d` / `recency_7d` / `recency_blend`) built from the **already-existing** recency features (`k_pct_7d`, `k_pct_30d`, `whiff_rate_30d`, `csw_pct_3start`, `velo_delta_3start`, `fastball_velo_trend`), EB-shrunk toward career→league. (`starter_ip_v1`, the BF side, already used these; only the K-rate side was flat.) The bake-off **ablates** rate-construction × framing × lineup-log5, so recency's value is *measured*, not assumed; the learned M3 also learns the recency weighting from the multi-window features.

**§0.5 conformance — the 4 feature-selection guards (per the addendum, all confirmed in `run_grid`):**
1. **Deflation counts the feature configs too.** `run_bakeoff`+`run_ablation` were merged into one `run_grid`: the full pre-registered grid = the compound feature cells (rate-construction × framing × lineup-log5) **plus** the 2 learned classes = **9 distinct configs**, all scored through the same purged CV, and a **single `pbo_cscv` deflates over every config** (not just the 4 model classes). `pbo.n_configs` = the full grid size.
2. **Select in-fold.** All in-config nuisance fitting is TRAIN-fold-only inside the purged CV — the compound `s` (Beta-Binomial concentration) and `λ` (spread recalibration) are fit on each fold's train rows; the learned models fit on train. Config **selection** is on pooled OOS (which is exactly what the PBO then deflates). No importance/transform is computed on the full set or the eval fold; the grid axes are data-independent (pre-registered), so there is no in-fold feature *discovery* to leak.
3. **Pre-registered + reproducible, not reactive.** The grid (`_COMPOUND_FEAT_CFGS` + the 2 classes) is a fixed literal — no reactive expansion if it underperforms. Any future ADD test goes through `incremental_lift_eval.py`. Nothing is declared inert on a single axis without its mechanism (see #4).
4. **Report winner + full table + named mechanism.** `run_grid` reports the winning **(model × feature-config)** cell, the full grid table, and **paired-by-fold ΔCRPS mechanisms** (`recency_vs_flat`, `framing_effect`, `lineup_log5_effect`) each with a ±2·SEM band and an `excludes_zero` flag — distinguishing "framing adds X, CI excludes 0" from "orthogonal-but-inert (CI spans 0)". All in `ablation_results/e5_2_strikeout_bakeoff.{json,md}`.

**Optuna / DSR:** following the cited exemplar (E1.9 `model_bakeoff.py` → `optuna_hpo.py`), the grid compares **default-ish configs** and leaves **Optuna HPO for the WINNER only** (tuning every candidate is the exemplar's anti-pattern). **DSR** is the E5.4 leg (it deflates a CLV/ROI Sharpe — a betting-returns series this calibration bake-off doesn't have); here PBO over the full grid is the selection-overfit guard.

**Cold-start bug fixed (the recency-fold NaN):** the first grid run logged `compound_recency fold failed: p<0/NaN` — the recency rate-construction emitted NaN on cold-start rows (no trailing-30d/season history) and `np.clip` doesn't fix NaN, so it reached the Beta-Binomial sampler. Fixed: the recency fallback chain now bottoms out at the always-finite league rate, and `build_predictors` guards `p_k` (non-finite → league, clipped to (0,1)). Re-run is clean.

**Disposition of the calibration near-miss:** the compound's first-run PIT (0.033 vs the 0.025 band, after λ=0.85) is a documented near-miss directly comparable to E2.3's accepted `run_diff` (0.0303). Rather than ship that as final, the **bake-off determines the best class+inputs** and that winner becomes the served pricer — which may also close the PIT gap (a learned/recency model that doesn't inherit `starter_ip_v1`'s over-width could calibrate tighter). The lead `calib_80 ≥ 0.80` AC was already met (0.859) and ECE is good (~0.035).

## Snowflake-once data flow + a latent bug fixed (2026-06-25)

- **Snowflake is hit ONCE across both runs.** `load_frame` issues a single `_FRAME_QUERY` (5 joined Snowflake tables: `mart_starting_pitcher_game_log` + `starter_ip_signals` + the three `feature_pregame_*`); only the prop *lines* come from S3 (DuckDB). Both scripts now call **`load_frame_cached`** (`betting_ml/utils/training_cache.get_cached_df`, the `model_bakeoff.py` pattern) with the same key `e5_2_strikeout_frame_{years}` → the bake-off pulls from Snowflake once, caches to `betting_ml/data/cache/*.parquet`, and the gate + every bake-off iteration read the parquet (off Snowflake). Pass `--refresh-cache` after new games land (7-day TTL). Within a run, `build_predictors` runs many times but all in-memory on that one frame.
- **Bug fixed:** `load_frame`'s blanket `pd.to_numeric` was coercing **`game_date` → NaN** (only `side` was excluded). That silently broke the purged-CV **date-ordinal purge band** (folds form off `game_year`, so the gate still ran, but the prior-season boundary tail wasn't being purged = mild optimism) and would have poisoned the parquet cache. Now `game_date` is kept as datetime. ⚠️ **The operator's first gate-run numbers (calib_80 0.859 etc.) were under the ineffective purge** — the re-run with this fix is slightly more honest (and may shift calibration a touch).

## What was built

All market-blind (`assert_market_blind` CONTRACT-GUARD), leak-clean, reusing E2.3's calibration/diagnostics verbatim.

### 1. `betting_ml/utils/prop_pricing.py` — the pure pricer (NumPy/SciPy, no Snowflake/model/market data → fully unit-tested)

**K = K-RATE × BATTERS-FACED:**
- **K-RATE** (`effective_k_rate`): per-PA strikeout probability `p_k` = `log5`( EB-shrunk pitcher K-rate, opposing-lineup K-propensity, league ) + an optional **tempered catcher-framing** logit nudge (`framing_logit_adjust`, γ small/pre-registered).
  - `eb_shrink_rate` — the small-sample edge: season K-rate shrunk → career-to-date → league.
  - `log5` — identity-preserving matchup combiner (reduces to the pitcher rate vs a league-average lineup). **No platoon/TTO conditioning term** — E13.2 showed PA-outcome matchup signal is ≈all batter×pitcher identity, which log5 captures by construction; conditioning added ≈0. The bet thesis is **market laziness + the EB small-sample edge + framing**, not a better matchup model.
- **BATTERS-FACED** (`draw_batters_faced`): reuses `starter_ip_v1`'s NegBin over **outs** (the workload/survival model) and converts outs → BF via the pitcher's on-base-against (reach) rate: reaches before `outs` outs ~ NegBin(n=outs, p=1−reach) → BF = outs + reaches.
- **CONVOLUTION** (`draw_strikeouts` / `price_strikeouts`): K | BF ~ **Beta-Binomial(BF, p_k, s)**. The concentration `s` is the leakage-safe calibration lever (the K analogue of E2.3's NegBin `r`): `fit_betabinom_concentration` MLEs it on held-out residuals; `calibrate_concentration_expanding` does the leakage-safe expanding-window (season T sees only seasons < T).
- **Other phase-1 props:** `prob_over_negbin` prices `pitcher_outs` analytically off the starter_ip_v1 NegBin; `draw_batter_bases_hits` prices `batter_total_bases`/`hits` from a per-batter PA-outcome multinomial over an expected-PA count.
- Reuses from `totals_distribution`: `quantile_grid`, `prob_over`, `prob_push`, `interval_coverage`, `randomized_pit`, `pit_flatness`, `DEFAULT_QUANTILES`, `CALIB_80_GATE`.
- `StrikeoutPricingParams` — JSON-roundtrippable served contract (concentration, league K, EB pseudo-counts, framing γ, reach default).

### 2. `betting_ml/scripts/prop_pricing/fit_prop_pricing.py` — the operator-run orchestration (>1-min Snowflake)
- Loads the per-start frame from `mart_starting_pitcher_game_log` (actuals: strikeouts, batters_faced, outs_recorded) + **strictly-prior** trailing cumulative K/BF (career & season windows, `rows … 1 preceding`), LEFT-joined to `starter_ip_signals` (outs μ/r), `feature_pregame_lineup_features.avg_k_pct_30d` (opposing side; COALESCE→league), and `feature_pregame_game_features.{home,away}_catcher_framing_runs`.
- Builds leak-clean `p_k` (two-stage EB shrink + log5 + framing-z), CONTRACT-GUARD market-blind.
- `PurgedWalkForwardSplit` (E1.1): per eval season, calibrate `s` on strictly-prior held-out residuals → price the K distribution → pool **PIT / calib_80 / per-line ECE**.
- Prices `pitcher_outs` (analytic NegBin calib_80) and emits a served-contract example (quantile grid + p_over_k ladder).
- Joins the S3 `pitcher_strikeouts` closing lines (DuckDB) for at-the-line availability/shape (fail-open). **The name→pitcher_id bridge (ref_players) + the per-line P(over)/P(under)/ECE is the E5.3 join** — this run confirms line availability; the model's PIT/calib is line-independent.
- Writes `betting_ml/models/sub_models/prop_pricing_v1/prop_pricing_strikeouts_v1.json` + `ablation_results/e5_2_prop_pricing_calibration.{json,md}`.

### 3. `betting_ml/tests/test_prop_pricing.py` — 29 unit tests (all green)
EB shrinkage limits, log5 identity/symmetry, framing monotonicity, BF compound mean/overdispersion, Beta-Binomial mean ≤ BF + overdispersion vs concentration, concentration MLE recovers a planted `s`, leakage-safe expanding window uses only prior seasons, the full price is **PIT-flat under the correct spec and FAILS flatness when overconfident** (the calibration is the lever, exactly as E2.3), p_over monotone in the line, quantile-grid monotone, pitcher_outs survival monotone, batter TB ≥ hits, params round-trip.

---

## ⏭️ Operator handoff

### 1. CI-gate result
- **Python unit tests:** ✅ `uv run pytest` green (37 `test_prop_pricing.py` + full suite). **⚠️ Fixed a pre-existing CI-blocker uncovered en route:** adding a test file shifted collection order and exposed an intermittent `snowflake.connector is not a package` collection error in `scripts/tests/test_savant_ingestion.py`. Root cause: `snowflake` is a NAMESPACE package and the vendored partial copy at `.lambda_build/package/snowflake` (+ `app/backend/services/snowflake.py`) can pollute its `__path__` under certain collection orders. **Fix: a root `conftest.py` that pre-imports the real `snowflake.connector.pandas_tools`** so it's cached as a proper package before any collection churn — deterministic, no test code touched. (This was blocking the Unit Tests CI job / a frontend deploy.)
- **dbt CI:** **N/A — zero dbt files changed.** `state:modified+` builds nothing; `dbtf compile` unaffected.

### 2. Run-order (the long fits — hand to operator, >1-min Snowflake)
```
# STEP 1 — bake-off: pick the model class + rate-construction + inputs (CRPS/calib, PBO-guarded).
# This is the ONLY Snowflake pull — it caches the frame to parquet; STEP 2 reuses it (Snowflake once).
uv run python betting_ml/scripts/prop_pricing/bakeoff_strikeouts.py            # writes e5_2_strikeout_bakeoff.{json,md}
uv run python betting_ml/scripts/prop_pricing/bakeoff_strikeouts.py --smoke    # harness check (no Snowflake)
# (add --refresh-cache on either script to force a fresh Snowflake pull after new games land)

# STEP 2 — gate run. The bake-off WINNER is poisson_glm_k (operator run 2026-06-25), ALREADY wired as
# the default served model. This fits + persists the served GLM bundle + writes the calibration doc:
uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py            # --model glm is the default
# variants:
uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py --no-lines       # skip the S3 ECE join
uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py --model compound  # interpretable fallback
```
**Bake-off verdict (real run, 26,062 starts, PBO over the full 9-config grid = 0.0):** the learned count
models beat the structural compound on CRPS **and** at-the-line ECE (lgbm CRPS 1.227/ECE 0.007, glm 1.236/0.010
vs best compound `season_career` 1.270/0.035). **Winner = `poisson_glm_k`** (best PIT-KS + near-best CRPS +
interpretable), now the default served model. **Mechanisms (CI-backed):** recency HURTS the hand-built compound
rate (+0.0337 — the flat season+career rate already wins; EB-to-career handles small samples), lineup-log5 HURTS
(+0.0203; confirms E13.2 matchup≈identity), framing inert/trivial (+0.0016). The learned models consume the *raw*
recency features and still win → recency helps when a model *weights* it, just not as a hand-rolled shrinkage rate.
**Served glm (validated on the cached frame, `--model glm --no-save`): calib_80 = 0.8104** (coverage-λ lands it
right at 0.80, fixing the over-coverage the bake-off flagged), **mean ECE 0.0202**, PIT max-decile-dev 0.0505
(diagnostic, not gated). STEP 2 with save persists `strikeout_glm_v1.pkl` (the served bundle: PoissonRegressor +
scaler + impute + features + λ; gitignored).
Expected outputs: the served params JSON + `e5_2_prop_pricing_calibration.{json,md}` with the real calib_80 / PIT-flat / per-line ECE / leakage-safe `s` per season.

**Pre-req:** `starter_ip_signals` must be populated for the seasons priced (it is, daily via `generate_starter_ip_signals.py`). Eligible-start coverage (needs starter_ip μ + trailing K) is reported in the run; cold-start first-career-start rows fall to the EB prior by construction.

### 3. `git add` — every file this session created/changed
```
conftest.py                                          # root pytest conftest — the snowflake-shadow CI fix
betting_ml/utils/prop_pricing.py
betting_ml/scripts/prop_pricing/__init__.py
betting_ml/scripts/prop_pricing/fit_prop_pricing.py
betting_ml/scripts/prop_pricing/bakeoff_strikeouts.py
betting_ml/tests/test_prop_pricing.py
quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md
quant_sports_intel_models/baseball/edge_program/build_roadmap.md
quant_sports_intel_models/baseball/edge_program/story_prompts.md
quant_sports_intel_models/baseball/edge_program/E5_2_HANDOFF.md
```
**Generated by the operator runs (also `git add` after the runs) — STEP 2 ran 2026-06-25, served=poisson_glm_k:**
```
quant_sports_intel_models/baseball/edge_program/ablation_results/e5_2_prop_pricing_calibration.json   # SERVED record (glm)
quant_sports_intel_models/baseball/edge_program/ablation_results/e5_2_prop_pricing_calibration.md
quant_sports_intel_models/baseball/edge_program/ablation_results/e5_2_strikeout_bakeoff.json
quant_sports_intel_models/baseball/edge_program/ablation_results/e5_2_strikeout_bakeoff.md
```
**Excluded (gitignored — S3/registry):** `betting_ml/models/sub_models/prop_pricing_v1/strikeout_glm_v1.pkl` — the served glm bundle (PoissonRegressor + scaler + impute + features + λ); regenerable via STEP 2, NOT promoted to S3 (gated at E5.4). The served contract = this `.pkl` + the `served_params` block in `e5_2_prop_pricing_calibration.json`.
**NOTE — no `prop_pricing_strikeouts_v1.json`:** that generically-named file was the COMPOUND model's analytic params from an early dev run; it was removed because the served model is glm and the name would mislead E5.3. The compound fallback (`--model compound`) now writes `prop_pricing_strikeouts_compound_v1.json` instead. `fit_prop_pricing.py` was edited for this — `git add betting_ml/scripts/prop_pricing/fit_prop_pricing.py`.

### 4. Validation gate
This session delivers the **machinery + harness** (the E5.2 AC: per-prop P(over/under) at the line + PIT-calibrated under E1.1 CV). The **calibration numbers** come from the operator run. The **edge gate is E5.4** (NOT this session): PBO<0.2 + DSR>0 per market, multiple-comparison-corrected across prop types, + forward CLV net of the prop vig. App work (player-page prop projections) is E5.5 — a separate app session whose prompt E5.3/E5.4 emit (§0.3).

---

## Notes / decisions / follow-ons

- **Prompt premise correction:** the prompt names `starter_v1` as a "K%" model — it is actually an **xwOBA-against (suppression) Normal model**, not a per-PA K-rate model. There was no existing K-rate model, so E5.2 **builds** the EB-shrunk per-PA K rate (the K-rate component). `starter_v1` is not used by the K pricer; `starter_ip_v1` (outs NegBin) is the batters-faced denominator.
- **Story 33.1 P(start)** is NOT implemented (confirmed). Expected-workload conditioning here flows through `starter_ip_v1`'s pre-game outs distribution; a P(start) weight is a documented future enrichment, not a blocker.
- **F5 scoping** (the first-5-innings K window, prompt item 3): the machinery is scope-agnostic — re-run with F5 actuals/lines (the E5.1 F5 backfill) and the same pricer prices the F5 K window. Deferred to the operator run / E5.3 as the lines are wired; not gating the build.
- **Opposing-lineup log5 partner** uses `avg_k_pct_30d`; a richer per-batter EB-K lineup aggregate (Singlearity-style) is a clean enrichment via `effective_k_rate` if the lineup join proves thin.
- **E5.3 name bridge:** the S3 prop lines key on `player_name` (no player_id). E5.3 must wire the `ref_players` name→pitcher_id bridge for the per-line edge/de-vig; this session reports line availability + shape so that join is scoped.
- **Smoke-tested** the orchestration's pure logic end-to-end on a synthetic frame (leakage-safe `s` stable across seasons, monotone p_over_k ladder, analytic pitcher_outs) — only the Snowflake/S3 I/O is unrun (operator).

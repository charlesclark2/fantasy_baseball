# MLB Edge-E7.3 — MiLB → MLB translation factors (MLEs)

**Model:** `milb_mle_v1` · **generated:** 2026-07-26T06:22:25.171697+00:00

> ⚠️ **This is an MLB-equivalent PRIOR/projection, not an edge claim.** It translates a player's pre-debut MiLB rate line (+ AAA Statcast where present) into a projected MLB rate line, measured against realized early-career MLB production — never a market. `best_alpha = 0` holds. The uncertainty is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a calibrated predictive interval — **E7.5 (wiring the prior into the EB posteriors) MUST recalibrate on held-out data before pricing** (the E13.6 pattern). The MiLB→MLB signal is genuine but MODEST (a small, self-selected graduated-player population): a ROBUST-BUT-WEAK result (low PBO, DSR possibly <0.95) is a VALID, VALUABLE feeder — reported honestly, not forced (P1.2b DSR-0.821).

## 1. Join coverage (the P1.2b dead-bridge check)

Does the MiLB `player_id` actually bridge to a realized MLB `batter_id` line? The map trains only on graduated players carrying BOTH a thick pre-debut minor line AND a realized MLB label; a silently-thin bridge under-trains it.

|                      |   value |
|:---------------------|--------:|
| n_rows_player_level  | 20453   |
| n_players            |  9747   |
| n_with_minor_line    | 12466   |
| n_graduated_labelled |  1750   |
| n_prospects          | 10716   |
| pct_graduated        |     8.6 |
| n_with_statcast      |  1393   |

Labelled graduates by level: `{'Double-A': 559, 'Triple-A': 458, 'High-A': 428, 'Single-A': 305}`

## 1b. Headline read — which skills translate

Each metric is its own translation, and the honest finding is that they **DIFFER sharply**. A metric is a **strong** feeder when its winner beats BOTH the level-mean null AND the generic archetype prior out-of-sample AND clears DSR≥0.95; **weak-but-real** when it beats both but DSR<0.95 (a valid feeder, P1.2b precedent); **no-signal** when the winner does not beat the null / archetype (the minor line adds nothing beyond which level the player reached → the emission degrades to the population prior).

| metric | winner            | oos_corr | dsr   | verdict                                        |
|:-------|:------------------|---------:|------:|:-----------------------------------------------|
| woba   | partial_pool@4.0  |    0.220 | 0.032 | ❌ no-signal (degrades to the population prior) |
| k_pct  | partial_pool@2.0  |    0.637 | 1.000 | ✅ STRONG feeder                                |
| bb_pct | partial_pool@4.0  |    0.491 | 0.989 | ✅ STRONG feeder                                |
| iso    | partial_pool@2.0  |    0.429 | 0.679 | 🟡 weak-but-real                               |

**The result is itself the deliverable — plate DISCIPLINE translates, the composite does not.** K% (corr 0.64) and BB% (corr 0.49) clear the strict live-grade deflation bar (DSR≥0.95, PBO 0.000) and beat both the null and the generic archetype prior decisively — plate discipline is the most stable, translatable minor-league skill and is the real MLE moat. ISO (power, corr 0.43) is weak-but-real (beats null + archetype, robust PBO 0.043, but doesn't clear DSR≥0.95 — park/pitching-quality dependent). **wOBA carries NO translatable signal beyond level**: the winner ties the level-mean null AND the population archetype prior (0.0285 vs 0.0284) — the run-value composite regresses hard on call-up and the graduated-hitter population is narrow (survivorship), so knowing a player's level + the population mean is as good as their minor wOBA.

⭐ **`partial_pool` (the shared `hierarchical.py` solver) WON every metric** — over the classic `multiplicative` Davenport factor foil (which UNDERperformed the null on wOBA/ISO) and the GBM+AAA-Statcast (competitive but never beat partial-pool; the Statcast add earns nothing over the discipline signal). The Bayesian partial-pooling form is validated; the classic multiplicative-factor MLE is refuted on this data.

> **For E7.5 (wiring the MiLB prior into `eb_batter_posteriors`):** wire the **K% and BB%** MLEs (strong), and **ISO** with wide uncertainty (weak-but-real); do **NOT** wire the **wOBA** MLE — it is no better than the incumbent generic archetype prior. Whichever are wired MUST be recalibrated on held-out data before pricing (PARAMETER uncertainty; E13.6). The bridge is healthy (1,750 graduated players; not a dead join).

## 2.woba — bake-off: `woba`  (winner: `partial_pool@4.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `woba` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| level_mean              |    0.0284 |              0.0000 | False        |
| archetype_prior         |    0.0284 |             -0.0000 | False        |
| partial_pool@4.0        |    0.0285 |             -0.0002 | True         |
| partial_pool@2.0        |    0.0286 |             -0.0002 | True         |
| gbm@300-2-0.03+sc       |    0.0289 |             -0.0006 | True         |
| gbm@500-3-0.02+sc       |    0.0295 |             -0.0011 | True         |
| multiplicative          |    0.0361 |             -0.0077 | True         |
| identity_no_translation |    0.0479 |             -0.0195 | False        |

- ✅ per-(player, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.270, 0.406], sd≤0.089)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ ⚠️ winner does NOT beat the null (MAE 0.0285 ≥ 0.0284) — honest no-signal
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0285 vs 0.0479)
- ✅ vs generic k≈200 population prior: MLE winner does NOT beat it (MAE 0.0285 vs 0.0284)
- ✅ PBO = 0.243 over 8 configs (see report — tie vs overfit)
- ✅ DSR = 0.032 (n_trials=8) — robust-but-weak, honest feeder (OK)
- 📈 OOS projection↔realized `woba` correlation (graduated players): **0.220**

## 2.k_pct — bake-off: `k_pct`  (winner: `partial_pool@2.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `k_pct` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@2.0        |    0.0394 |              0.0108 | True         |
| partial_pool@4.0        |    0.0394 |              0.0108 | True         |
| gbm@300-2-0.03+sc       |    0.0397 |              0.0104 | True         |
| gbm@500-3-0.02+sc       |    0.0407 |              0.0095 | True         |
| multiplicative          |    0.0468 |              0.0034 | True         |
| archetype_prior         |    0.0495 |              0.0007 | False        |
| level_mean              |    0.0502 |              0.0000 | False        |
| identity_no_translation |    0.0586 |             -0.0084 | False        |

- ✅ per-(player, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.101, 0.469], sd≤0.086)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0394 < 0.0502)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0394 vs 0.0586)
- ✅ vs generic k≈200 population prior: MLE winner beats it (MAE 0.0394 vs 0.0495)
- ✅ PBO = 0.000 over 8 configs (<0.2 ✅)
- ✅ DSR = 1.000 (n_trials=8) — ≥0.95
- 📈 OOS projection↔realized `k_pct` correlation (graduated players): **0.637**

## 2.bb_pct — bake-off: `bb_pct`  (winner: `partial_pool@4.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `bb_pct` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@4.0        |    0.0185 |              0.0026 | True         |
| partial_pool@2.0        |    0.0185 |              0.0026 | True         |
| gbm@300-2-0.03+sc       |    0.0191 |              0.0020 | True         |
| gbm@500-3-0.02+sc       |    0.0196 |              0.0015 | True         |
| archetype_prior         |    0.0207 |              0.0004 | False        |
| level_mean              |    0.0211 |              0.0000 | False        |
| multiplicative          |    0.0211 |             -0.0000 | True         |
| identity_no_translation |    0.0308 |             -0.0097 | False        |

- ✅ per-(player, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.036, 0.157], sd≤0.091)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0185 < 0.0211)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0185 vs 0.0308)
- ✅ vs generic k≈200 population prior: MLE winner beats it (MAE 0.0185 vs 0.0207)
- ✅ PBO = 0.000 over 8 configs (<0.2 ✅)
- ✅ DSR = 0.989 (n_trials=8) — ≥0.95
- 📈 OOS projection↔realized `bb_pct` correlation (graduated players): **0.491**

## 2.iso — bake-off: `iso`  (winner: `partial_pool@2.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `iso` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@2.0        |    0.0396 |              0.0028 | True         |
| partial_pool@4.0        |    0.0396 |              0.0027 | True         |
| gbm@300-2-0.03+sc       |    0.0396 |              0.0027 | True         |
| gbm@500-3-0.02+sc       |    0.0403 |              0.0020 | True         |
| archetype_prior         |    0.0420 |              0.0004 | False        |
| level_mean              |    0.0423 |              0.0000 | False        |
| multiplicative          |    0.0472 |             -0.0048 | True         |
| identity_no_translation |    0.0509 |             -0.0086 | False        |

- ✅ per-(player, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.055, 0.333], sd≤0.087)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0396 < 0.0423)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0396 vs 0.0509)
- ✅ vs generic k≈200 population prior: MLE winner beats it (MAE 0.0396 vs 0.0420)
- ✅ PBO = 0.043 over 8 configs (<0.2 ✅)
- ✅ DSR = 0.679 (n_trials=8) — robust-but-weak, honest feeder (OK)
- 📈 OOS projection↔realized `iso` correlation (graduated players): **0.429**

## 3. Limitations

- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks confidence correctly, too tight to price. E7.5 MUST recalibrate on held-out data (E13.6).
- **Per-(player, level) rows share the player's MLB label** — a correlated-observation limit; it is what lets the model estimate LEVEL factors. The deflation (PBO/DSR) + partial-pool shrinkage guard against reading too much into thin level×league cells.
- **Graduated players are a SELF-SELECTED population** (they reached the MLB PA floor) — the map is calibrated on players who established, which is the population the prior is used for (a rookie getting playing time). Survivorship is stated, not corrected.
- **The AAA-Statcast add is coverage-conditioned** (AAA-only, 2022+) — only the GBM reads it, impute-flagged; a player/season without it is honest-null, never fabricated.
- **Realized MLB label is Statcast-era-bounded** (`mart_batter_rolling_stats` is 2015+) — `--season-floor 2015` keeps the minor lines in the same era as the labels.
- **Empirical-Bayes plug-in** (partial-pool): variance components are point estimates, not integrated over — the same posture as P1.2 / MLB's bullpen posteriors.
- **best_alpha = 0** — a Dynasty projection + a betting prior, not a market bet.


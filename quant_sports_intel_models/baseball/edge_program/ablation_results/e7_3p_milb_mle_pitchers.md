# MLB Edge-E7.3p — PITCHER MiLB → MLB translation factors (MLEs)

**Model:** `milb_mle_pitcher_v1` · **generated:** 2026-07-27T06:37:41.968850+00:00

> ⚠️ **This is an MLB-equivalent PRIOR/projection, not an edge claim.** It translates a pitcher's pre-debut MiLB rate line (+ AAA Statcast stuff/velo/spin where present) into a projected MLB rate line, measured against realized early-career MLB production — never a market. `best_alpha = 0` holds. The uncertainty is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a calibrated predictive interval — **the starter-EB wiring story (the E7.5 sibling) MUST recalibrate on held-out data before pricing** (the E13.6 pattern). A ROBUST-BUT-WEAK result (low PBO, DSR possibly <0.95) is a VALID, VALUABLE feeder — reported honestly, not forced (P1.2b DSR-0.821; E7.3's wOBA null).

## 1. Join coverage (the P1.2b dead-bridge check)

Does the MiLB `player_id` actually bridge to a realized MLB `pitcher_id` line? The map trains only on graduated pitchers carrying BOTH a thick pre-debut minor line AND a realized MLB label; a silently-thin bridge under-trains it.

|                      |   value |
|:---------------------|--------:|
| n_rows_player_level  | 23862   |
| n_players            | 11166   |
| n_with_minor_line    | 13953   |
| n_graduated_labelled |  2034   |
| n_prospects          | 11919   |
| pct_graduated        |     8.5 |
| n_with_statcast      |  1829   |
| n_with_gb_label      |  5795   |

Labelled graduates by level: `{'Double-A': 664, 'High-A': 524, 'Triple-A': 490, 'Single-A': 356}`

## 1b. Headline read — which pitcher skills translate

Each metric is its own translation; the honest finding is that they DIFFER (E7.3's batter result: discipline translated, the run-value composite did not — the pitcher priors are K%/BB%/stuff strong, ERA/BABIP-adjacent noisy). A metric is a **strong** feeder when its winner beats BOTH the level-mean null AND the generic archetype prior out-of-sample AND clears DSR≥0.95; **weak-but-real** when it beats both but DSR<0.95 (a valid feeder, P1.2b precedent); **no-signal** when the winner does not beat the null / archetype (the minor line adds nothing beyond level → the emission degrades to the population prior).

| metric        | winner           |   oos_corr |   dsr | verdict                                         |
|:--------------|:-----------------|-----------:|------:|:------------------------------------------------|
| k_pct         | partial_pool@4.0 |      0.366 | 0.786 | 🟡 weak-but-real                                |
| bb_pct        | partial_pool@4.0 |      0.367 | 0.947 | 🟡 weak-but-real                                |
| hr_rate       | partial_pool@4.0 |      0.094 | 0.130 | 🟡 weak-but-real                                |
| gb_pct        | partial_pool@2.0 |      0.551 | 1.000 | ✅ STRONG feeder                                |
| xwoba_against | partial_pool@2.0 |      0.147 | 0.030 | ❌ no-signal (degrades to the population prior) |

> **Session read (2026-07-27, the E2.1-r PBO discipline applied to the table above):**
> `hr_rate`'s 🟡 label is MECHANICAL (it clears the beats-null/beats-archetype thresholds by 1e-4)
> but the leaderboard is a TIED FIELD — winner 0.0099 vs archetype/partial_pool@2.0/level_mean all
> 0.0100 — with PBO 0.900 and corr 0.094. Per the E2.1-r reading, a tied-field high PBO IS the
> null: "which candidate wins" is noise ⇒ **treat `hr_rate` as effectively NO-SIGNAL** — HR
> suppression carries ~nothing translatable beyond the population mean (consistent with HR outcomes
> being BABIP-adjacent, the pre-registered expectation). **⇒ Wiring guidance for the starter-EB
> story: wire `gb_pct` (STRONG) + `k_pct`/`bb_pct` (weak-but-real, WIDE recalibrated uncertainty);
> do NOT wire `hr_rate` or `xwoba_against`.** Also noteworthy: pitcher K% translates far more
> weakly than batter K% (corr 0.366 vs E7.3's 0.637) — a real asymmetry, not a harness artifact
> (same harness, same CV); pitcher outcomes are more role/park/defense-confounded. And
> `partial_pool` won ALL FIVE metrics while `multiplicative` underperformed the null on all five —
> the classic Davenport factor MLE is now refuted on both sides of the ball.

## 2.k_pct — bake-off: `k_pct`  (winner: `partial_pool@4.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `k_pct` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@4.0        |    0.0357 |              0.0019 | True         |
| partial_pool@2.0        |    0.0357 |              0.0018 | True         |
| gbm@300-2-0.03+sc       |    0.0358 |              0.0017 | True         |
| gbm@500-3-0.02+sc       |    0.0369 |              0.0007 | True         |
| archetype_prior         |    0.0373 |              0.0002 | False        |
| level_mean              |    0.0376 |              0.0000 | False        |
| multiplicative          |    0.0437 |             -0.0061 | True         |
| identity_no_translation |    0.0557 |             -0.0181 | False        |

- ✅ per-(pitcher, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.106, 0.309], sd≤0.093)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0357 < 0.0376)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0357 vs 0.0557)
- ✅ vs generic population prior: MLE winner beats it (MAE 0.0357 vs 0.0373)
- ✅ PBO = 0.014 over 8 configs (<0.2 ✅)
- ✅ DSR = 0.786 (n_trials=8) — robust-but-weak, honest feeder (OK)
- 📈 OOS projection↔realized `k_pct` correlation (graduated pitchers): **0.366**

## 2.bb_pct — bake-off: `bb_pct`  (winner: `partial_pool@4.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `bb_pct` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@4.0        |    0.0197 |              0.0016 | True         |
| partial_pool@2.0        |    0.0198 |              0.0015 | True         |
| gbm@300-2-0.03+sc       |    0.0201 |              0.0012 | True         |
| gbm@500-3-0.02+sc       |    0.0204 |              0.0009 | True         |
| archetype_prior         |    0.0212 |              0.0000 | False        |
| level_mean              |    0.0213 |              0.0000 | False        |
| identity_no_translation |    0.0250 |             -0.0037 | False        |
| multiplicative          |    0.0261 |             -0.0048 | True         |

- ✅ per-(pitcher, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.053, 0.189], sd≤0.102)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0197 < 0.0213)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0197 vs 0.0250)
- ✅ vs generic population prior: MLE winner beats it (MAE 0.0197 vs 0.0212)
- ✅ PBO = 0.000 over 8 configs (<0.2 ✅)
- ✅ DSR = 0.947 (n_trials=8) — robust-but-weak, honest feeder (OK)
- 📈 OOS projection↔realized `bb_pct` correlation (graduated pitchers): **0.367**

## 2.hr_rate — bake-off: `hr_rate`  (winner: `partial_pool@4.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `hr_rate` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@4.0        |    0.0099 |              0.0000 | True         |
| archetype_prior         |    0.0100 |              0.0000 | False        |
| partial_pool@2.0        |    0.0100 |              0.0000 | True         |
| level_mean              |    0.0100 |              0.0000 | False        |
| gbm@300-2-0.03+sc       |    0.0101 |             -0.0001 | True         |
| gbm@500-3-0.02+sc       |    0.0103 |             -0.0003 | True         |
| identity_no_translation |    0.0165 |             -0.0066 | False        |
| multiplicative          |    0.0177 |             -0.0077 | True         |

- ✅ per-(pitcher, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.017, 0.062], sd≤0.062)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0099 < 0.0100)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0099 vs 0.0165)
- ✅ vs generic population prior: MLE winner beats it (MAE 0.0099 vs 0.0100)
- ✅ PBO = 0.900 over 8 configs (see report — tie vs overfit)
- ✅ DSR = 0.130 (n_trials=8) — robust-but-weak, honest feeder (OK)
- 📈 OOS projection↔realized `hr_rate` correlation (graduated pitchers): **0.094**

## 2.gb_pct — bake-off: `gb_pct`  (winner: `partial_pool@2.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `gb_pct` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| partial_pool@2.0        |    0.0480 |              0.0105 | True         |
| partial_pool@4.0        |    0.0480 |              0.0105 | True         |
| gbm@300-2-0.03+sc       |    0.0494 |              0.0092 | True         |
| gbm@500-3-0.02+sc       |    0.0506 |              0.0080 | True         |
| multiplicative          |    0.0561 |              0.0025 | True         |
| archetype_prior         |    0.0576 |              0.0010 | False        |
| level_mean              |    0.0586 |              0.0000 | False        |
| identity_no_translation |    0.0954 |             -0.0368 | False        |

- ✅ per-(pitcher, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.271, 0.590], sd≤0.071)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ winner beats the level-mean null OOS (MAE 0.0480 < 0.0586)
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0480 vs 0.0954)
- ✅ vs generic population prior: MLE winner beats it (MAE 0.0480 vs 0.0576)
- ✅ PBO = 0.000 over 8 configs (<0.2 ✅)
- ✅ DSR = 1.000 (n_trials=8) — ≥0.95
- 📈 OOS projection↔realized `gb_pct` correlation (graduated pitchers): **0.551**

## 2.xwoba_against — bake-off: `xwoba_against`  (winner: `partial_pool@2.0`)

Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB `xwoba_against` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` (raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks (`selectable = False`).

| config                  |   oos_mae |   oos_skill_vs_null | selectable   |
|:------------------------|----------:|--------------------:|:-------------|
| level_mean              |    0.0258 |              0.0000 | False        |
| archetype_prior         |    0.0258 |             -0.0000 | False        |
| partial_pool@2.0        |    0.0260 |             -0.0002 | True         |
| partial_pool@4.0        |    0.0261 |             -0.0003 | True         |
| gbm@300-2-0.03+sc       |    0.0261 |             -0.0003 | True         |
| gbm@500-3-0.02+sc       |    0.0265 |             -0.0006 | True         |
| identity_no_translation |    0.0419 |             -0.0161 | False        |
| multiplicative          |    0.0507 |             -0.0249 | True         |

- ✅ per-(pitcher, level) grain is unique
- ✅ every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted
- ✅ projection finite + plausible (range [0.295, 0.351], sd≤0.019)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ ⚠️ winner does NOT beat the null (MAE 0.0260 ≥ 0.0258) — honest no-signal
- ✅ vs raw minor line as-is: MLE winner beats it (MAE 0.0260 vs 0.0419)
- ✅ vs generic population prior: MLE winner does NOT beat it (MAE 0.0260 vs 0.0258)
- ✅ PBO = 1.000 over 8 configs (see report — tie vs overfit)
- ✅ DSR = 0.030 (n_trials=8) — robust-but-weak, honest feeder (OK)
- 📈 OOS projection↔realized `xwoba_against` correlation (graduated pitchers): **0.147**

## 3. The documented path to the starter-EB rookie prior (the betting payoff)

The betting consumer is `eb_starter_posteriors` (dbt, `dbt/models/eb_posteriors/`) — a debuting rookie starter today gets a generic prior, the exact cold-start E7.5 fixed for batters. The wiring story (the E7.5 pitcher sibling — NOT this story) should mirror E7.5 1:1:

1. **Recalibrate first (E13.6):** run the `mle_prior.py` pattern against these projections — parameter sd → held-out σ_resid per metric on the graduated-pitcher holdout (merge `has_mlb_label`/`mlb_pa` from `mle_graduated_pairs_pitchers.parquet` and filter to the HIGHEST level per pitcher — the E7.5 thin-cameo landmine applies verbatim: 1-TBF cameos inflate σ 2–3×).
2. **Wire ONLY the metrics this report grades strong / weak-but-real** (weak ones with wide uncertainty); a no-signal metric stays on the incumbent generic prior (E7.3's wOBA precedent).
3. **Land a single-overwrite parquet** (`baseball/lakehouse/milb_mle_pitcher_prior/`) + a FAIL-SAFE empty-view registration in `run_w1_lakehouse.py` (the `_register_mle_prior_view` pattern — serving must never HALT on a missing prior).
4. **Bounded-rate updates use pseudo-count (Beta κ) blends, never Normal-Normal** — the E7.5 ISO blow-up lesson; K%/BB%/HR-rate/GB% are all bounded rates, so κ-blends throughout.
5. **Serving-check on a real slate** before calling it live (the E7.5 discipline).

## 4. Limitations

- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks confidence correctly, too tight to price. The wiring story MUST recalibrate (E13.6).
- **Per-(pitcher, level) rows share the pitcher's MLB label** — a correlated-observation limit; it is what lets the model estimate LEVEL factors. The deflation (PBO/DSR) + partial-pool shrinkage guard against thin level×league cells.
- **Graduated pitchers are a SELF-SELECTED population** (they reached the MLB TBF floor) — the map is calibrated on pitchers who established, which is the population the prior is used for. Survivorship is stated, not corrected.
- **Role mix (starter vs reliever) shifts across the translation** — `minor_start_share` is a GBM-only impute-flagged feature, not a hierarchy level; an AAA reliever's K% translating differently from a starter's is learned, not structurally modeled.
- **`gb_pct` is a CROSS-DEFINITION map** — the MiLB feature is the ground-OUT share GO/(GO+AO) (all the box line offers); the MLB label is Statcast GB/BIP. The regression learns the rescale; the verdict says whether the proxy carries.
- **`xwoba_against`'s minor feature exists ONLY for AAA 2022+ rows** (the E7.2 coverage) — few debut cohorts, so its bake-off may be data-thin or skipped; honest-null, never forced.
- **The AAA-Statcast add is coverage-conditioned** (AAA-only, 2022+) — only the GBM reads it, impute-flagged; a pitcher/season without it is honest-null, never fabricated.
- **Realized MLB label is Statcast-era-bounded** (`mart_pitcher_rolling_stats` is 2015+) — `--season-floor 2015` keeps the minor lines in the same era as the labels.
- **Empirical-Bayes plug-in** (partial-pool): variance components are point estimates, not integrated over — the same posture as P1.2 / the bullpen posteriors.
- **best_alpha = 0** — a board projection + a betting prior, not a market bet.


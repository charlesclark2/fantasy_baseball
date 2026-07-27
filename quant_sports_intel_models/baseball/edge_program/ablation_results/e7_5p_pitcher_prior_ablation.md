# MLB Edge-E7.5p — PITCHER MiLB MLE → recalibrated rookie-STARTER prior (wired into `eb_starter_posteriors`)

**Model:** `milb_mle_pitcher_prior_v1` · **generated:** 2026-07-27T07:31:32.332313+00:00

> ⚠️ **This wires a performance-based PRIOR for cold-start starters, not an edge claim.** A debuting / low-BF rookie starter previously shrank toward a GENERIC experience-band prior; E7.5p replaces that with the E7.3p MiLB→MLB MLE line for the pitcher metrics that TRANSLATE — **GB% (strong), K% and BB% (weak-but-real, wide)** — and shrinks the rookie's own MLB line toward it as batters-faced accrue. **HR-rate and xwOBA-against are NOT wired** (E7.3p: a tied-field null and a no-signal translation). The E7.3p parameter sd is too tight to price, so E7.5p RECALIBRATES it on held-out MLB data (E13.6). `best_alpha = 0`.

> 📉 **Expectation-set (recorded up front, per the story):** pitcher K% translates FAR more weakly than batter K% (E7.3p OOS corr **0.366** vs E7.3's **0.637** — same harness, same CV, so a real asymmetry: pitcher outcomes are more role/park/defense-confounded). The rookie-STARTER prior's lift is therefore expected to be **MORE MODEST than the batter version's**, and the biggest single contribution should come from **GB% (contact management, corr 0.551 / DSR 1.000)** — not K%. Anything larger than that would be the surprising result, and would deserve suspicion first.

## 1. Recalibration — parameter sd → held-out predictive spread (E13.6)

`σ_resid = std(realized MLB rate − MLE mean)` over graduated pitchers (leakage-safe: each `mle_<m>` was fit only on strictly-prior debut cohorts). It REPLACES the tighter parameter sd `mle_<m>_sd`. The pseudo-count κ = m(1−m)/σ_resid² − 1 (clipped) is the prior's weight in the metric's own EVIDENCE UNITS — batters faced for K%/BB%, balls in play for GB%. Coverage of ±σ_resid / ±1.645σ_resid against the honest ~0.68 / ~0.90 shows the recalibrated sd is calibrated, not the tight one.

| metric   |   resid_sd |   param_sd_median |   tightness_ratio |   n |   coverage_68 |   coverage_90 |   label_sampling_sd |   true_sd_est |   kappa_floor |   kappa_cap | evidence_unit   |
|:---------|-----------:|------------------:|------------------:|----:|--------------:|--------------:|--------------------:|--------------:|--------------:|------------:|:----------------|
| gb_pct   |   0.059254 |          0.007626 |             7.77  | 815 |        0.6675 |        0.8982 |            0.034103 |      0.048457 |            20 |         400 | bip             |
| k_pct    |   0.044676 |          0.005769 |             7.744 | 815 |        0.7313 |        0.8994 |            0.023298 |      0.03812  |            20 |         400 | bf              |
| bb_pct   |   0.024746 |          0.004281 |             5.78  | 815 |        0.7178 |        0.9043 |            0.016718 |      0.018245 |            20 |         400 | bf              |

- `tightness_ratio` = σ_resid ÷ median parameter sd (>1 confirms the E7.3p parameter sd was too tight to price).
- `true_sd_est` = variance-decomposed between-pitcher prior sd (σ_resid² − label-sampling-var); a diagnostic only — the SERVED prior sd stays σ_resid (conservative: a marginally weaker prior, so the rookie's own MLB line takes over a touch faster — the safe direction).
- **Thin-cameo floor (the E7.5 landmine, verbatim):** rows are kept only at `has_mlb_label` (`mlb_pa ≥ 150` TBF); GB% additionally requires `mlb_bip ≥ 50`. Without the floor σ_resid inflates ~1.7–2.2× on all three metrics and the prior would be needlessly weak.

## 2. Calibration ablation — MLE prior vs the incumbent generic prior (purged, leave-one-cohort-out)

For each debut cohort Y (≥1 strictly-prior cohort): the GENERIC baseline mean = the population mean of the realized MLB metric over PRIOR cohorts (what the generic experience-band prior collapses to at BF≈0 — E7.3p's `archetype_prior` benchmark); the MLE mean = the OOS `mle_<m>`. Each method uses its OWN prior-cohort residual sd (both self-calibrated → the comparison is calibration × SHARPNESS, not a sd handicap). Scored on the cohort-Y rookie starters. Lower NLL/CRPS/MAE = better; coverage ≈ 0.68/0.90 = honest.

| metric   |   n_scored |   n_cohorts |   mle_nll |   generic_nll |   mle_crps |   generic_crps |   mle_mae |   generic_mae |   mle_cov68 |   generic_cov68 |   mle_cov90 |   generic_cov90 | mle_wins   | notes   |
|:---------|-----------:|------------:|----------:|--------------:|-----------:|---------------:|----------:|--------------:|------------:|----------------:|------------:|----------------:|:-----------|:--------|
| gb_pct   |        716 |          10 |  -1.40909 |      -1.14752 |   0.033535 |       0.043477 |  0.047673 |      0.061873 |      0.6732 |          0.6578 |      0.9106 |          0.898  | True       | []      |
| k_pct    |        716 |          10 |  -1.68744 |      -1.57598 |   0.02474  |       0.0276   |  0.034272 |      0.038177 |      0.7277 |          0.7388 |      0.898  |          0.9176 | True       | []      |
| bb_pct   |        716 |          10 |  -2.27025 |      -2.19015 |   0.013812 |       0.014956 |  0.019103 |      0.02083  |      0.7165 |          0.7109 |      0.9064 |          0.9064 | True       | []      |

- **gb_pct** — ✅ MLE prior improves rookie-starter calibration: NLL -1.4091 vs -1.1475, CRPS 0.03353 vs 0.04348, MAE 0.04767 vs 0.06187 (n=716 rookie starters over 10 cohorts).
- **k_pct** — ✅ MLE prior improves rookie-starter calibration: NLL -1.6874 vs -1.5760, CRPS 0.02474 vs 0.02760, MAE 0.03427 vs 0.03818 (n=716 rookie starters over 10 cohorts).
- **bb_pct** — ✅ MLE prior improves rookie-starter calibration: NLL -2.2702 vs -2.1902, CRPS 0.01381 vs 0.01496, MAE 0.01910 vs 0.02083 (n=716 rookie starters over 10 cohorts).

## 3. What is wired (and what is not)

- **Served build:** `dbt/models/eb_posteriors/eb_starter_posteriors.sql` (DuckDB branch — the SF-free lakehouse compute; the Snowflake branch is a thin `select *` over the ext table). A `milb_mle_pitcher_prior` precursor view (this script's S3 output) is joined on `pitcher_id` (MLBAM).
- **COLD-START GATE (this is stricter than the batter sibling, on purpose):** the MLE prior is applied ONLY to a starter with NO qualifying prior MLB experience (`n_prior_seasons = 0`, i.e. `age_band = 'u25'` — fewer than 10 career prior starts AND under 150 career prior BF). The E7.3p map is calibrated on a pitcher's FIRST TWO MLB seasons; applying a 2015 minor-league line to an established starter would be out-of-distribution. An experienced starter keeps the incumbent band prior / IL-return blend, unchanged.
- **κ-BLEND EVERYWHERE, never Normal-Normal (the E7.5 ISO lesson, applied pre-emptively):** all three wired metrics are bounded rates, so the MLE update is the pseudo-count blend `(m·κ + obs·n)/(κ + n)` — K%/BB% with n = current-season BF (the existing accrual), GB% with n = prior-season balls in play. A Normal-Normal update with a measurement-variance floor lets a tiny-sample extreme observation overwhelm the prior; a variance floor cannot save it.
- **`eb_gb_pct` is a NEW served column.** The starter EB table carried no ground-ball metric at all, so GB% — the STRONGEST pitcher translation — had nowhere to land. It is populated for EVERY starter (MLE prior for cold-start pitchers, prior-season league GB% mean otherwise), shrunk toward the pitcher's own prior-season GB% weighted by balls in play. **It has no downstream consumer yet** — wiring it into `feature_pregame_starter_features` means retraining the models that read that feature block (the E7.9 train/serve-consistency class), which is a separate story. K% and BB% flow to serving IMMEDIATELY through the existing `starter_eb_k_pct` / `starter_eb_bb_pct` features.
- **`eb_xwoba_against` is UNTOUCHED** — E7.3p graded that translation no-signal, so the experience-band prior stays (E7.3's wOBA precedent).
- **Leakage-safe:** only pre-debut minor-league stats enter the MLE (the E7.3p as-of guard); the observed GB% component joins on `game_year = season − 1` (the repo's batted-ball leakage doctrine); the prior table is static, read as a W8a precursor view.
- **Fail-safe:** the precursor view degrades to an EMPTY typed view when the parquet is absent → every MLE column reads NULL → the generic prior is used everywhere (exactly pre-E7.5p behaviour). A missing artifact can NEVER HALT the serving-critical W8a build.

## 4. Limitations

- **Pitcher translations are weaker than batter translations** — see the expectation-set note above. GB% is the only STRONG feeder; K%/BB% are weak-but-real and carry a WIDE recalibrated σ_resid, which is exactly why the κ they imply is small enough for a rookie's own line to take over quickly.
- **`gb_pct` is a CROSS-DEFINITION map** (inherited from E7.3p): the MiLB feature is the ground-OUT share GO/(GO+AO); the MLB label — and the served observed component — is Statcast GB/BIP. The regression learned the rescale; both served sides use the Statcast definition.
- **The observed GB% component is PRIOR-SEASON, not season-to-date.** `mart_pitcher_batted_ball_profile` is season-grain, so a within-season as-of GB% would require a pitch-level re-aggregation; joining on `season − 1` is the leakage-safe doctrine used by every other batted-ball consumer here. Consequence: a veteran's `eb_gb_pct` does not move during the season.
- **σ_resid carries finite-sample label noise** → the prior is marginally weaker than truth (safe).
- **Graduated pitchers are self-selected** (they reached the TBF floor) — the calibration is on pitchers who established, which is the served population. Stated, not corrected (from E7.3p).
- **Coverage:** 7474 pitchers carry a calibrated prior (6659 of them prospects with no MLB debut yet — the population the cold-start gate actually serves).
- **Not wired, with reasons:**
  - `hr_rate` — E7.3p TIED FIELD (winner beats the null by 1e-4, PBO 0.900, corr 0.094) — the E2.1-r reading makes this effectively NO-SIGNAL; HR suppression is BABIP-adjacent.
  - `xwoba_against` — E7.3p no-signal (corr 0.147, DSR 0.030; does NOT beat the generic archetype prior) — the batter-wOBA mirror. eb_xwoba_against keeps its experience-band prior.
- **best_alpha = 0** — a cold-start betting prior, never a market bet.

## 5. Train/serve consistency (the E7.9 class) — read before promoting

The served models that consume `starter_eb_k_pct` / `starter_eb_bb_pct` (via `feature_pregame_starter_features` → `feature_pregame_game_features_raw`) were **TRAINED on the OLD generic-prior values**. E7.5p changes those two features for exactly one slice of rows — COLD-START starters — so a model sees a feature drawn from a slightly different distribution than it was fit on. Three things bound the exposure, and one follow-up closes it:

1. **Bounded slice.** Only `n_prior_seasons = 0` starters move at all; every experienced starter's row is byte-identical (pinned by a test). Cold-start starters are a small share of any slate.
2. **Bounded magnitude.** The change is a PRIOR swap, not a scale change: both the old band prior and the new MLE mean live in the same range, and the κ-blend converges to the pitcher's own line as BF accrue — the divergence is largest at BF≈0 and decays from there.
3. **Direction is toward truth.** §2 is the evidence that the new value is BETTER calibrated for exactly those rows; a stale model reading a better-calibrated input is a smaller error than the same model reading a worse one, though it is not zero.

**The close-out is a RETRAIN of the starter-consuming models after this lands and a few weeks of cold-start rows have accrued** — the same posture E7.5 took on the batter side. Until then the honest framing is: improved cold-start CALIBRATION in the EB layer, with the downstream models still carrying their old fit. **This is also why `eb_gb_pct` is deliberately NOT joined into `feature_pregame_starter_features` yet** — adding a brand-new feature to a trained model's input block is the strong form of the same problem, and belongs with the retrain.


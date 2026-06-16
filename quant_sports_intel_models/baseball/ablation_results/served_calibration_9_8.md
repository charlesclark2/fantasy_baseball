# Story 9.8 — Served predictive-distribution calibration audit

**Date:** 2026-06-16 · **Harness:** `betting_ml/scripts/served_calibration_audit_9_8.py` (per-target JSON in
`betting_ml/evaluation/calibration_9_8/`) · **Method:** controlled walk-forward (train <Y, eval Y), same tuned HP,
two served tiers (`champion` = full post-lineup contract, `pre_lineup` = 33.0 Class-A floor). Regression via
`promotion_gate.calibration_report` (coverage / PIT-KS / NLL / CRPS / bias); classification via ECE + reliability +
logistic recalibration slope (raw XGB vs served Platt). **MEASURE-ONLY — no model change.**

## Headline verdict (honest-2026 surface = the decision-relevant one)

**All three targets serve CALIBRATED predictive distributions on 2026.** Every `⚠ MISCAL` flag is on a COMPLETED
2024/2025 fold and reflects a *historical regime artifact*, not current serving.

| Target | Tier | 2026 cov80 (gap) | cov90 | PIT-KS | bias | Verdict |
|---|---|---|---|---|---|---|
| total_runs | champion | 0.808 (+0.008) | 0.899 | 0.048 | −0.073 | **calibrated ✓** |
| total_runs | pre_lineup | 0.789 (−0.011) | 0.895 | 0.049 | −0.054 | **calibrated ✓** |
| run_diff | champion | 0.776 (−0.024) | 0.877 | 0.019 | −0.008 | **calibrated ✓** |
| run_diff | pre_lineup | 0.776 (−0.024) | 0.877 | 0.030 | −0.114 | **calibrated ✓** |
| home_win | champion | ECE 0.040, slope 1.16 | — | — | — | borderline (see §home_win) |
| home_win | pre_lineup | ECE 0.047, slope 1.15 | — | — | — | borderline (see §home_win) |

## total_runs — calibrated; the historical over-bias is gone on 2026
- 2026: coverage dead-on nominal (cov80 ~0.79–0.81, cov90 ~0.895–0.90), PIT-KS ~0.048, level bias tiny (−0.05/−0.07).
- 2024/2025 flags: bias **+0.20/+0.22** (the historical totals over-prediction) → flips to level-unbiased on 2026.
  Fingerprint of the **27.7 season-norm** contact→runs regime fix; not a current-serving defect.
- ⚠️ The "+0.40 totals over-bias" in the Epic 17 record is a DIFFERENT model (PyMC NegBin LTV, Jensen floor) — do
  not conflate with this NGBoost point/predictive champion, which is level-unbiased on 2026.
- Consistent with **29.1**: totals is level-unbiased but per-game variance-deficient *vs the market* — i.e. the
  predictive is honestly calibrated to its OWN errors (80% PI really holds 80%) but **wider than the market line**.
  Calibrated-but-not-sharp, NOT miscalibrated.

## run_diff — calibrated on 2026; mild 2024 overconfidence
- 2026: cov80 0.776 (gap −0.024, inside tol), PIT-KS very low (0.019–0.030), bias ~0 (champion −0.008; pre_lineup −0.114).
- 2024 flag: OVERCONFIDENT (cov80 ~0.715, PI ~8pts too tight) — a high-variance run-environment season the model
  under-spread for; 2025/2026 well-covered. Historical, not current.

## home_win — base classifier mildly UNDERCONFIDENT; the SERVED path is a deliberate identity (A2.9)
- Base classifier (`p_home_win_classifier`, what this audit fit): ECE ~0.018–0.031 on completed folds (good),
  ~0.040–0.047 on noisy 2026 (n=792). Consistent **slope ≈ 1.06–1.16 > 1 = mild underconfidence** (probs slightly
  compressed toward 0.5). **Platt is a wash-to-harmful** (in-sample-fit on the eval fold; helps some folds, HURTS the
  pre_lineup-2026 tier: raw 0.0387 < Platt 0.0469) — a single sigmoid can't fix an *under*confidence well.
- **BUT the served h2h decision prob is NOT this layer.** `predict_today` serves
  `calibrated_win_prob = live_calibrator(0.5·ngboost_P_home + 0.5·platt_classifier)`. The live `calibrator.joblib`
  (`train_calibrator.py`, Card 7.C/8.O) is the decision layer, and **Story A2.9 (2026-06-10) already audited it and
  set it to IDENTITY** to preserve spread (`calibrator_refit_meta.json`): recalibrators *did* lower ECE but only by
  COLLAPSING discrimination (`old_live_calibrator`: ECE 0.020 but Brier 0.240, spread 0.019 — crushed toward 0.5).
- **⇒ Do NOT recommend new home_win recalibration.** A2.9 settled the ECE-vs-discrimination tradeoff (identity wins for
  betting). This audit's mild-underconfidence finding *argues against* a shrinking recalibrator anyway. Optional
  low-priority follow-on: a spread-preserving *sharpening* (temperature T<1, slope-correcting) — but only if a live
  re-audit shows it beats identity on Brier WITHOUT collapsing spread (the A2.9 floor).

## σ / uncertainty CONSUMER annotations (AC2)
- **`combined_sigma`** (load_layer3_features, Story 9.7) — feeds on run_diff/totals predictive widths, both
  **calibrated ✓** on 2026 → safe as a decision input. (It's a blend of per-game PI widths + disagreement; the PI
  components are honest.)
- **Story 30.15 pick_explanation uncertainty / served PIs** — **calibrated ✓** on 2026 for both regression targets;
  safe to surface to users. home_win attribution is on the (deliberate-identity) served prob — fine.
- **Story 22.4 σ-aware selection/sizing** — **GREEN-LIT** to consume the run_diff/totals predictive σ. Note the
  totals predictive is *calibrated-but-wide* (29.1) → uncertainty-aware selection will correctly ABSTAIN often on
  totals (wide PI relative to any edge); that is the truthful stance, not a bug.
- **Epic 12.4 conviction signals** — the edge/σ inputs they consume are calibrated on 2026 → train on honest inputs.

## Recommendations
1. **No model/calibration change required for decision use** — all served posteriors are calibrated on 2026.
2. **home_win** — leave the A2.9 identity live-calibrator as is. Optional low-pri: spread-preserving sharpening,
   gated on a live re-audit vs the A2.9 Brier/spread floor.
3. **Watch the historical regime artifacts** — totals 2024/25 over-bias + run_diff 2024 overconfidence are corrected
   on 2026 (season-norm). If ever training without 27.7 season-norm, the totals bias returns.
4. **22.4 is cleared to proceed** on the calibration prerequisite.

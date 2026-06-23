# Story E13.6 — H2H win-probability calibration / reliability audit

**Date:** 2026-06-21 · **Objective metric = Brier / log-loss / ECE (NOT CLV).** The H2H edge is
dead (E3.1/E4/E1.9/E13.1) and we do not claim it. This story asks one question: **is the
win-probability we SHOW honest — when we say 58%, does home win ~58%?**

**Harness:** `betting_ml/scripts/h2h_calibration_audit_e13_6.py` (JSON →
`betting_ml/evaluation/calibration_e13_6/served_calibration_v5.json`). **Surface audited:** the
SERVED prob `daily_model_predictions.calibrated_win_prob` (= identity-calibrated consensus
`0.5·ngboost + 0.5·xgb-Platt`) for the **current champion v5** (the 2026-06-12 market-blind,
de-leaked re-promotion), 2026 honest-OOS, joined to `betting.mart_game_results.home_team_won`,
one row/game (prefer post_lineup, latest). **MEASURE + candidate only — live calibrator untouched.**

## Headline verdict — the served H2H prob is OVERCONFIDENT and miscalibrated

**The number we surface is not honest today.** On 1,138 settled 2026 games the served win-prob
spreads predictions across 0.10–0.91 but realized outcomes barely move:

| served pred bin | avg_pred | actual home-win | n |
|---|---|---|---|
| 0.1–0.2 | 0.168 | 0.394 | 66 |
| 0.2–0.3 | 0.256 | 0.497 | 173 |
| 0.3–0.4 | 0.351 | 0.494 | 182 |
| 0.4–0.5 | 0.450 | 0.542 | 155 |
| 0.5–0.6 | 0.546 | 0.597 | 196 |
| 0.6–0.7 | 0.648 | 0.533 | 120 |
| 0.7–0.8 | 0.752 | 0.562 | 160 |
| 0.8–0.9 | 0.837 | 0.550 | 80 |

A "75%" home pick wins **56%**; a "25%" home pick wins **50%**. The realized rate is ~flat near
the 0.53 base rate across the whole prediction range → **wide spread (0.20) = false precision.**

### Scores vs context baselines (lower is better; market shown for CONTEXT, not a beat-claim)

| predictor | n | Brier | log-loss | ECE |
|---|---|---|---|---|
| **served model (v5)** | 1138 | **0.2761** | **0.7585** | **0.1541** |
| no-skill base rate (0.53) | 1138 | 0.2489 | 0.6910 | 0.000 |
| no-skill coin-flip (0.50) | 1138 | 0.2500 | 0.6931 | 0.033 |
| served model (odds games) | 567 | 0.2673 | 0.7393 | 0.137 |
| de-vigged market | 567 | 0.2469 | 0.6867 | 0.033 |

**The served prob is WORSE than a no-skill base-rate predictor on every proper score**
(Brier 0.276 vs 0.249, log-loss 0.759 vs 0.691) and far worse calibrated (ECE 0.154 vs ~0). The
market is well-calibrated (ECE 0.033) and modestly beats no-skill. The model's corr with outcome
is **0.073** — essentially no live discrimination.

## Segments — the miscalibration is SYSTEMIC, not one bad cell

ECE 0.12–0.26 and corr ≈ 0 in **every** segment (home favorite/dog, every month, every
run-environment). Two cuts matter most:

- **`pred:home_lean (p>0.55)`** → model mean 0.707, actual 0.557 (ECE 0.152). **`pred:away_lean
  (p<0.45)`** → model mean 0.303, actual 0.483 (ECE 0.180). Overconfident symmetrically in both
  tails — the signature of a too-wide confidence map, not a directional bias.
- **`tier:post_lineup_live`** (FULL feature coverage, cov 0.99, n=107): ECE **0.263**, corr −0.04.
  Even the dense, lineup-confirmed serve is overconfident with no skill → the overconfidence is
  **not only** morning serving-sparsity (30.3); the de-leaked v5's *live* H2H skill is genuinely
  near-zero. (Consistent with "the H2H edge is dead" and an intrinsically near-coin-flip sport.)

## Why this REVERSES the A2.9 "identity" conclusion (and why both are correct)

A2.9 (2026-06-10) deliberately set the live calibrator to **identity** — recalibrators lowered
ECE only by COLLAPSING spread, which is bad **for betting**. E13.6 finds the opposite recommendation,
and the two do not conflict — they evaluate **different surfaces under different objectives**:

| | A2.9 (betting lens) | E13.6 (calibration lens) |
|---|---|---|
| surface | dense **re-scored** consensus | **SERVED** prob (product truth) |
| model | old **376-dim** (identifier + market **leak**) | **v5 market-blind, de-leaked** (6/12) |
| corr w/ outcome | ~0.46 (leak-inflated) | **0.073** (honest) |
| shrinking a calibrator | destroys REAL discrimination → reject | removes FALSE precision → improves |

The leak that inflated A2.9's discrimination was removed in 30.1/30.4 (→ v5). The served prob no
longer has discrimination to protect, so the identity pass-through now just **preserves
overconfidence**. The calibrator was last validated on a model that no longer exists.

## Recalibration candidates (chronological hold-out)

| method | Brier | log-loss | ECE | spread | corr |
|---|---|---|---|---|---|
| identity (live) | 0.2802 | 0.7683 | 0.1745 | 0.2092 | 0.072 |
| **Platt** | **0.2468** | **0.6868** | **0.0265** | 0.0351 | 0.072 |
| isotonic | 0.2483 | 0.6936 | 0.0738 | 0.0857 | 0.084 |
| temperature (T=6.09) | 0.2488 | 0.6907 | 0.0530 | 0.0397 | 0.076 |

Any recalibration **materially improves** Brier (0.280→0.247, now ≈ market/no-skill) and ECE
(0.175→0.027). But because there is no real signal to preserve, calibration is achieved only by
**shrinking the prob to a narrow band around the base rate (spread 0.21→0.035)**. The fitted
temperature **T = 6.09** quantifies the overconfidence: the served logits must be divided by ~6×.
**An honestly-calibrated H2H prob on this model is essentially ~0.48–0.56 — a coin-flip with a
small home tilt.** That is the truthful product, even though it is far less exciting than 0.84.

## Honest variance framing for the app (deliverable AC4)

Copy the product should adopt (no win-rate / edge claims; transparency wedge, GTM §1):

> **Single MLB games are close to coin-flips.** Even sharp markets rarely price a side beyond
> ~55–58%, and over a full season our model's home/away calls land near a coin-flip once you
> account for how each game actually turns out. We show a calibrated estimate — when we say 54%,
> the home team wins about 54% of the time — and a credible range around it, rather than a
> falsely-precise number. Use it as a lean, not a lock.

Concretely: surface the **calibrated (shrunk) win-prob** as the headline number, keep the
`win_prob_ci_low/high` band visible, and never display a confident-looking extreme (0.80+) that
the data cannot support.

## DECISION SHIPPED (PM, 2026-06-21) — temperature recalibration promoted

Per the product owner: **recalibrate now via temperature (not disclose-only, not a permanent
Platt bake-in).** Temperature over Platt because the fit-set is contaminated by 30.3
serving-skew — a 2-param logistic risks fitting the contamination, while the 1-param monotone
temperature is robust, preserves game ranking, and is trivially re-fit after the serving fix.

- **Promoted:** `TemperatureCalibrator(T=6.30)` (class in `betting_ml/utils/calibration.py` so the
  pickle resolves in predict_today/backfill) → `calibrator.joblib` + versioned
  `calibrator_temperature_v1.joblib`. Fit on the v5 served sample (n=1138; the live-only set
  n=113 railed the optimizer to the bound — too small to trust alone, so the broad v5 sample,
  which is the model the post_lineup serve uses, is the robust interim fit-set).
- **Effect on served prob:** ECE 0.154→**0.033**, Brier 0.276→**0.249**, log-loss 0.759→**0.691**,
  spread 0.202→**0.037**. Example map: served 0.85→**0.57**, 0.75→**0.54**, 0.25→**0.46**. The
  honest displayed band is **~0.43–0.57**.
- **No betting impact:** H2H `best_alpha=0` already collapses actionable edges to ~0; shrinking
  `calibrated_win_prob` only narrows the (already non-actionable) diagnostic edge and the
  displayed prob. run_diff/totals are untouched.
- **Re-fit guard (registry `calibrator_refit_required_after`):** INTERIM measure — mandatory
  re-audit/re-fit after Epic 33 dense serving, the 30.3 serving-completeness fix, OR the E1.9 v6
  promotion. The honest band may legitimately WIDEN (T→1) once the model serves on complete
  features. `pre_lineup_v1` gets its own temperature once it accrues ~150+ settled live games.
- **Disclosure framing** (lean-not-lock + visible CI + variance copy) → filed as an **E9 app
  follow-on** in `story_prompts.md` (frontend scope).

## Recommendation rationale (superseded by the shipped decision above)

1. **The served H2H prob must not ship as-is** — it is overconfident (ECE 0.154) and a worse
   probability forecast than guessing the base rate. This is a product-honesty problem.
2. A spread-honest recalibration (**Platt** best on both Brier and ECE; temperature is the
   minimal-assumption alternative) fixes it, at the cost of a near-flat band — which is the
   *honest* representation of a near-coin-flip sport with a de-leaked, low-discrimination model.
3. **Caveat — do not silently bake in the serving bug.** Part of the overconfidence is 30.3
   serving-skew (point-in-time sparsity), which Epic 33 / 30.3 aim to fix. A static Platt fit on
   today's served distribution would over-shrink once dense serving is restored. So this
   recalibration is an **interim honesty measure**, re-audited after any serving fix or the v6
   rebuild (E1.9). The durable fix is serving + a genuinely-discriminating model, not a calibrator.
4. Candidate written to `betting_ml/models/home_win/calibrator_e13_6_candidate.joblib`
   (**not promoted** — the live calibrator is untouched, mirroring A2.9). Promotion changes a live
   product number → requires the changelog entry + app verification, hence the decision below.

**Open product decision (operator):** ship the spread-honest recalibration now (honest narrow
band + variance framing), OR keep identity and instead DISCLOSE the uncertainty in-app (widen the
shown CI + variance copy) while the serving/v6 fix lands. Both are defensible; (1) is the
straighter read of "the surfaced number must be calibrated."

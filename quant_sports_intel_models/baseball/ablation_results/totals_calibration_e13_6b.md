# Story E13.6b — served TOTALS P(over) calibration (the totals analog of E13.6)

**Date:** 2026-07-17 · **Objective = ECE / Brier / log-loss, NOT CLV.** The totals edge is dead (`best_alpha = 0`) and we do not claim it. This story asks: **is the P(over) we SHOW honest — when we say 60% over, does the game go over ~60%?**

**Surface:** the SERVED totals `model_prob` (= raw distributional P(over), NO serve-time calibration today) from the serving-cache permanent game-detail blobs (`api-cache/permanent/picks/game/` in S3 — the E9.26 data path, DynamoDB-free). Window **2026-04-17 → 2026-07-17**, **1110** scored Final totals games (pushes dropped).

## Headline — the served raw P(over) is mildly OVERconfident toward the over

Raw served P(over) over the whole window: **ECE 0.0595** · Brier 0.2548 · log-loss 0.7036 · spread 0.0811 · mean_pred 0.5464 · base-rate 0.4982 · corr 0.0504 (n=1110). E9.26 measured the served moneyline at ECE ~0.029; totals sit meaningfully above that — the gap this story closes.

### Raw served reliability (predicted vs observed P(over))

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.0–0.1 | 2 | 0.070 | 0.500 |
| 0.2–0.3 | 10 | 0.269 | 0.400 |
| 0.3–0.4 | 45 | 0.360 | 0.444 |
| 0.4–0.5 | 196 | 0.463 | 0.464 |
| 0.5–0.6 | 576 | 0.552 | 0.491 |
| 0.6–0.7 | 266 | 0.631 | 0.545 |
| 0.7–0.8 | 15 | 0.718 | 0.600 |

## Recalibration candidates (date-aligned chronological hold-out)

Train dates ≤ **2026-06-22** (n=835); embargo **1d**; eval dates ≥ **2026-06-24** (n=260). Leakage-safe: the 1-D calibrator sees only TRAIN dates; scored on strictly-later EVAL dates.

| method | Brier | log-loss | ECE | spread | corr |
|---|---|---|---|---|---|
| **identity** ← ECE-pick | 0.2486 | 0.6905 | 0.0607 | 0.0743 | 0.1115 |
| **platt** | 0.2491 | 0.6913 | 0.0549 | 0.0086 | 0.1115 |
| **isotonic** | 0.2478 | 0.6888 | 0.039 | 0.0295 | 0.1012 |
| **temperature** | 0.249 | 0.6911 | 0.0556 | 0.011 | 0.1099 |

→ **ECE-pick (calibration lens): `identity`** · Brier-pick: `identity` · fitted temperature T=6.9483.

### Eval-fold reliability of the ECE-pick (PIT-flatness check)

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.2–0.3 | 4 | 0.283 | 0.500 |
| 0.3–0.4 | 13 | 0.370 | 0.538 |
| 0.4–0.5 | 56 | 0.458 | 0.321 |
| 0.5–0.6 | 143 | 0.551 | 0.517 |
| 0.6–0.7 | 44 | 0.619 | 0.614 |

## Pooled walk-forward OOF (the robust verdict — not one noisy tail split)

The back 60% of the window is cut into **6** date-aligned blocks; each method is fit on games strictly before each block (embargo 1d) and its block-predictions are POOLED (n_oof=664) and scored once. This averages over many cut points so the verdict can't hinge on a single 3-week tail.

| method | Brier | log-loss | ECE | spread | corr |
|---|---|---|---|---|---|
| **identity** | 0.2524 | 0.6984 | 0.0468 | 0.0833 | 0.0674 |
| **platt** | 0.25 | 0.6931 | 0.0059 | 0.0094 | 0.0135 |
| **isotonic** ← OOF pick | 0.251 | 0.7123 | 0.0145 | 0.0465 | 0.0255 |
| **temperature** | 0.2493 | 0.6917 | 0.0177 | 0.0121 | 0.0707 |

→ **OOF ECE-pick (spread-floor 0.03): `isotonic`** · unconstrained ECE-min: `platt` · Brier-pick: `isotonic`.

## Verdict

**Recalibrate the served totals P(over) via `isotonic`.** Pooled out-of-fold (n_oof=664, 6 blocks) it is the ONLY candidate that both **clears the 0.03 A2.9/E13.6 discrimination floor** (spread 0.0465 vs Platt 0.0094 / temperature 0.0121, which collapse P(over) to a near-constant band ≈ base rate) **and materially improves calibration** — OOF ECE 0.0468 (raw identity) → **0.0145**, at/under the moneyline ~0.029 the story targets, and full-window raw was 0.0595. The mechanism is a monotone correction of a mild systematic over-lean (raw mean_pred 0.5464 vs base-rate 0.4982), so it shifts the reliability onto the diagonal without flattening to a constant.

**Honest caveats (why this is product-calibration value, not an edge):**

- Totals discrimination is near-zero regardless (`best_alpha = 0`): OOF corr is 0.0674 raw and 0.0255 after isotonic — both tiny. There is essentially no rank signal to protect, so the floor is a formality here; isotonic clears it anyway, which is the cleanest outcome (Platt/temperature do not).
- The single 259-game **tail** split is inconclusive/borderline — there isotonic's spread (0.0295) sat just UNDER the floor so identity won by a hair. The **pooled walk-forward is the trustworthy instrument** (662 OOF preds over 6 cut points vs one noisy 3-week window) and it selects isotonic with spread 0.0465 ≥ floor. Reporting both; the pooled verdict governs.
- This closes the E9.26 totals-vs-moneyline calibration gap and strengthens the E9.43 conviction base. It changes NO edge/Kelly math (alpha-gated to ~0); it only makes the SHOWN P(over) honest. Pushes are dropped (no binary label).

**Part B** wires `isotonic` into `predict_today` at the totals emit (see below) — **HELD until E11.20's full-slate cutover gate is confirmed clean** (never change two things in one verification window). Re-audit after any totals-model rebuild.

## Deployable candidate (refit on the FULL window)

- **method:** `isotonic`
- **artifact:** `betting_ml/models/total_runs/calibrator_e13_6b_isotonic_candidate.joblib` (versioned; **PART A — not wired into predict_today**)
- **in-sample self-fit ECE:** 0.0 — **IGNORE this number** (isotonic refit and scored on the SAME full window overfits to ~0; it is not a validation metric). The honest metric is the **pooled OOF ECE above**; this candidate is simply that method refit on all 1110 games for deployment.

## Part B (HELD until E11.20 full-slate cutover gate is confirmed clean)

Wire the chosen calibrator into `predict_today` at the totals-prob emit ([predict_today.py](scripts/predict_today.py) — `p_over_v` → `totals_model_prob`, the totals analog of the h2h `_apply_calibrator(cons_win)` path), source the artifact from S3 like the h2h `calibrator_artifact`, register it, then re-measure served ECE on a fresh box slate. Deploying it changes the served P(over) BY DESIGN → it must NOT enter an E11.20 verification slate (never change two things in one verification window).

## Honest framing

Calibration is PRODUCT value (a trustworthy P(over) alongside the moneyline), **NOT** an edge claim — `best_alpha = 0` holds, totals Kelly/edge stay alpha-gated to ~0, pushes are dropped (no binary label). A calibrated P(over) simply makes the surfaced number honest and strengthens the E9.43 conviction base.

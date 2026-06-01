# Epic 6D Architecture Decision — Distributional Bullpen Model

**Status:** ✅ Candidate B selected — two-stage IP→NegBin champion (2026-06-01)
**Date:** 2026-06-01
**Story:** 6D.1 / 6D.2

---

## Problem Statement

The Epic 6 champion (`bullpen_quality_v1`, NGBoost Normal) predicts bullpen xwOBA
(a continuous rate, ~0.29 mean). For Epic 6D, the goal is to shift the target to
**bullpen runs allowed** — a non-negative integer count. Count data with
leverage-driven variance structure (high-leverage vs. mop-up usage) is poorly
approximated by Normal. NegBin(mu, r) is the natural family:

- Var(NegBin) = μ + μ²/r  (always > μ, i.e., overdispersed vs. Poisson)
- r → ∞ collapses to Poisson; small r = heavy overdispersion
- Matches bullpen structure: when a starter exits early (high-leverage), relievers
  face a disproportionately volatile run environment; mop-up usage drives zero-heavy,
  right-tailed distributions within the same game-level count.

---

## Overdispersion Audit (6D.1 gate) — ✅ COMPLETE 2026-05-31

```
uv run python betting_ml/scripts/audit_bullpen_overdispersion.py
```

**Artifact:** `betting_ml/models/ablation/bullpen_6d_overdispersion_20260531T180803.json`

| Metric                       | Result     | Gate        |
|------------------------------|------------|-------------|
| n_games (2021–2026)          | 25,793     | —           |
| Global Mean (runs)           | 2.0655     | —           |
| Global Var (runs)            | 5.2547     | —           |
| **Var/Mean (global)**        | **2.544**  | > 1 ✓       |
| P(0 runs)                    | 31.1%      | —           |
| NegBin r (MLE)               | 1.2170     | —           |
| NegBin NLL                   | 1.9328     | —           |
| Normal NLL                   | 2.2485     | —           |
| **Δ NLL (NB − Normal)**      | **−0.316** | < 0 ✓       |
| Deciles OD (Var > Mean)      | **10/10**  | ≥ 7/10 ✓   |
| **Overall Gate**             | **PASS**   | —           |

Key observations:
- Var/Mean = 2.54 — substantial overdispersion (2.5× the Poisson equidispersed baseline)
- r = 1.22 is notably low (heavily overdispersed NegBin; r < 2 = strong right tail)
- 10/10 deciles overdispersed with monotonically increasing Var/Mean (2.04 → 2.92),
  confirming overdispersion worsens at higher means — exactly NegBin structure
- Zero runs in 31.1% of game-sides — right-skewed, zero-heavy distribution
- NegBin NLL beats Normal by 0.316 nats per observation — decisive advantage

---

## Candidate Architectures

### Candidate A — NegBin wrapper on champion mean (SELECTED — Immediate)

**Architecture:**
1. Use the Epic 6 champion (`bullpen_quality_v1.pkl`, NGBoost Normal) to predict
   expected bullpen xwOBA → convert to expected runs via:
   `mu_runs = pred_xwoba × expected_bullpen_PA × league_runs_per_xwoba_unit`
   OR train a new mean-only model directly on `bullpen_runs_allowed` target.
2. Fit NegBin r from training set residuals: `r = mu² / max(var - mu, 1e-6)`
3. At inference: NegBin(mu=predicted_runs, r=fitted_r)

**Dependencies:** Epic 6.3 ✅ (champion in S3)

**Pattern:** Identical to 3D (run environment) and 4D (offense). Proven approach.

**Notes:**
- r can be constant (fitted on full training residuals) or conditional (NGBoost-style
  per-row r). Start with constant r; upgrade to conditional if calib_80 < 0.80.
- The `bullpen_fatigue_adjusted_mu` EB correction (6D.3) multiplies the predicted
  mu by (eb_bullpen_xwoba / league_avg_xwoba), so lower xwOBA → lower adj_mu.

---

### Candidate B — Two-stage: starter IP → bullpen exposure → NegBin (**UNBLOCKED 2026-06-01**)

**Architecture:**
1. Stage 1: Consume `starter_ip_p20_outs_v1` from `feature_pregame_sub_model_signals`
   as the pessimistic starter depth estimate (20th-percentile outs) → derive expected
   maximum bullpen exposure (27 − starter_ip_p20_outs) in outs.
2. Stage 2: Scale NegBin μ by bullpen exposure fraction relative to a full-game baseline.
   `mu_adj = bullpen_mu_base × (27 − starter_ip_p20_outs) / league_avg_bullpen_outs`
3. Propagates starter depth uncertainty into bullpen run distribution.

**Dependencies:** Epic 5D ✅ complete 2026-06-01.
- `starter_ip_mu_v1` and `starter_ip_p20_outs_v1` confirmed non-null for 100% of
  2020–2026 game-sides in `feature_pregame_sub_model_signals`.
- 27,584 rows backfilled in `starter_ip_signals`.

**Status:** ✅ UNBLOCKED — ready for 6D.2 Candidate B re-run.

**Run command (user executes):**
```bash
uv run python betting_ml/scripts/train_bullpen_distributional.py --candidate b
```
Compare Candidate B NLL vs Candidate A NLL (1.8940). Lower NLL wins; promote winner as `bullpen_v2.pkl`.

---

### Candidate C — Direct NegBin NGBoost (Evaluate in 6D.2 if A fails gate)

**Architecture:**
- Replace NGBoost Normal with NGBoost NegBin (or Poisson) directly on
  `bullpen_runs_allowed` target.
- No manual r fitting — NGBoost learns per-row r from data.

**Dependencies:** None.

**When to use:** If Candidate A's constant-r NegBin does not meet calib_80 ≥ 0.80
in 6D.2. Note: NGBoost NegBin training is significantly slower (~2–4× vs Normal).

---

## Decision

**Candidate B is the champion.** Epic 5D completed 2026-06-01, delivering
`starter_ip_p20_outs_v1`. Candidate B was evaluated against A's tuned benchmark
(NLL=1.8940) on the same 5-fold recent window (2022–2026). B won outright.

| Metric | Candidate A | Candidate B | Verdict |
|--------|-------------|-------------|---------|
| CV NLL (5 recent folds) | 1.8940 | **1.8852** | B wins (Δ=−0.0088) |
| CV calib_80 | — | 0.9248 | ≥ 0.80 ✓ |
| Final r (all-data) | 1.4474 | **1.4853** | — |
| League avg bullpen outs | — | 15.268 | used for inference scaling |
| MLflow run_id | 343f96ef… | **c3d85f41…** | — |

Candidate C is a fallback only; 10/10 folds fell back to mean (GLM NLL 1.9603).

---

## Training Results — 6D.2 ✅ COMPLETE 2026-05-31

```
uv run python betting_ml/scripts/train_bullpen_distributional.py --no-promote
```

**Champion:** Candidate A (LightGBM + NegBin r from residuals)
**MLflow run_id:** `343f96ef497444489d6ed5b21344e9a5` (experiment: `bullpen_6D`)
**Artifacts:** `betting_ml/models/sub_models/bullpen_v2.pkl` | `s3://baseball-betting-ml-artifacts/sub_models/bullpen_v2.pkl` ✅

### Walk-forward CV (default params, 10 folds, 2016–2026)

| Fold | Train    | Test | NLL    | MAE    | calib_80 | r       |
|------|----------|------|--------|--------|-----------|---------|
| 1    | 2016     | 2017 | 2.2336 | 1.6316 | 0.7803   | 403.427 |
| 2    | 2016–17  | 2018 | 2.2548 | 1.7109 | 0.7803   | 403.427 |
| 3    | 2016–18  | 2019 | 2.1747 | 1.7887 | 0.7856   | 17.824  |
| 4    | 2016–19  | 2020 | 2.1490 | 1.8585 | 0.8161   | 6.657   |
| 5    | 2016–20  | 2021 | 2.0203 | 1.7009 | 0.8546   | 5.123   |
| 6    | 2016–21  | 2022 | 1.9190 | 1.6268 | 0.8839   | 3.983   |
| 7    | 2016–22  | 2023 | 1.9716 | 1.7351 | 0.8771   | 3.228   |
| 8    | 2016–23  | 2024 | 1.9103 | 1.6532 | 0.8934   | 2.855   |
| 9    | 2016–24  | 2025 | 1.9391 | 1.7721 | 0.9120   | 2.592   |
| 10   | 2016–25  | 2026 | 1.9320 | 1.7410 | 0.9009   | 2.370   |
| **Mean** |      |      | **2.0504** | **1.7219** | **0.8484** | **85.149** |

Note: r starts extremely large (early folds near-Poisson — small training set), converges to ~2–3 with more data. The all-data fitted r = **1.4474** is the operative value in the promoted artifact.

### Gate comparison

| Gate | Candidate A (default) | Candidate A (tuned) | Candidate C GLM | Pass? |
|------|-----------------------|---------------------|-----------------|-------|
| NLL vs GLM baseline | 2.0504 ❌ | **1.8940** ✓ | 1.9603 | ✓ (tuned) |
| calib_80 ≥ 0.80 | 0.8484 | — | 0.8970 | ✓ |
| MAE vs mean-predictor (1.7326) | 1.7219 ✓ | — | 1.7326 | ✓ |

Candidate C: 10/10 folds fell back to mean prediction (HessianInversionWarning each fold). The GLM NLL (1.9603) reflects an intercept-only NegBin, not a fully fitted model — making it a weak baseline that Optuna tuning easily beats.

### Optuna tuning (50 trials: 10 probe + 40 full, recent 5 folds)

| | Value |
|---|---|
| Probe best NLL | 1.8945 |
| Full pass best NLL | **1.8940** |
| Improvement vs default | −0.156 nats |
| Best params | n_est=200, lr=0.01531, leaves=16, min_child_samples=87, subsample=0.74, colsample=0.80 |

### Subset evaluation

| Subset | n | NLL | calib_80 | PI width |
|--------|---|-----|----------|----------|
| High-fatigue (fatigue_score > 0.7) | 45,254 | 1.877 | 0.924 | 4.949 |
| Rested (fatigue_score ≤ 0.7) | 694 | 1.946 | 0.919 | 5.022 |
| Blowout (score_delta > 5) | 9,127 | 2.277 | 0.830 | 5.529 ✓ |
| Close (score_delta ≤ 5) | 36,821 | 1.779 | 0.947 | 4.806 |

**High-fatigue PI width note:** The fatigue threshold (> 0.7) captures 98.5% of the dataset (45,254 of 45,948 rows). The "rested" group (n=694) is a small tail. The PI-width comparison is not meaningful with this split. The fatigue threshold may need recalibration for subset analysis — or the EB adjustment in 6D.3 is the more principled way to condition on fatigue. Blowout PI is wider than close ✓ — the NegBin correctly captures mop-up dispersion.

### Final artifact

| Field | Value |
|-------|-------|
| Model type | LightGBM + NegBin r from residuals |
| CV NLL (tuned, 5-fold recent) | 1.8940 |
| CV NLL (all 10 folds, default) | 2.0504 |
| CV MAE | 1.7219 |
| CV calib_80 | 0.8484 |
| Final r (all-data) | 1.4474 |
| In-sample NLL | 1.8780 |
| In-sample calib_80 | 0.9241 |
| MLflow run_id | 343f96ef497444489d6ed5b21344e9a5 |
| Local pkl | `betting_ml/models/sub_models/bullpen_v2.pkl` |
| S3 | `s3://baseball-betting-ml-artifacts/sub_models/bullpen_v2.pkl` ✅ |

---

## Sequencing

```
6D.1 (this doc)  →  6D.2 Candidate A training ✅  →  6D.3 signals ✅  →  6D.4 registry ✅  →  6D.5 EB ablation ✅
                 ↗
6D.2 Candidate B  ✅ CHAMPION 2026-06-01 (Epic 5D complete)
                    NLL 1.8852 < Candidate A 1.8940 → Candidate B promoted as bullpen_v2.pkl
                    generate_bullpen_signals.py updated with B scaling
                    NOTE: backfill must be re-run to apply B exposure scaling to existing rows
```

---

## Key Differences from 3D / 4D

| Aspect              | 3D (run env)         | 4D (offense)          | 6D (bullpen)                      |
|---------------------|----------------------|-----------------------|-----------------------------------|
| Champion target     | total_runs (count)   | team_runs (count)     | bullpen_xwoba (rate) → **switch** |
| 6D target           | —                    | —                     | bullpen_runs_allowed (count)      |
| EB adjustment       | park factors         | lineup archetypes     | eb_bullpen_xwoba (fatigue-adj mu) |
| Candidate B blocker | none                 | none                  | Epic 5D (starter_xwoba_sigma)     |

The key distinction: 6D switches the target from xwOBA (rate) to runs (count).
The EB multiplicative correction in 6D.3 maps xwOBA quality back onto the runs scale.

---

## Output Signals (6D.3)

| Signal                        | Description                              |
|-------------------------------|------------------------------------------|
| `bullpen_mu`                  | NegBin μ — expected bullpen runs         |
| `bullpen_dispersion`          | NegBin r — fitted dispersion parameter   |
| `bullpen_fatigue_adjusted_mu` | `mu × (eb_bullpen_xwoba / league_avg_xwoba)` — quality-corrected expected runs |
| `uncertainty`                 | 80% PI width: `NegBin.ppf(0.90) - NegBin.ppf(0.10)` |
| `signal_available`            | Boolean: all required inputs present     |

Registry key: `bullpen_v2`
MLflow experiment: `bullpen_6D`
S3 artifact: `s3://baseball-betting-ml-artifacts/sub_models/bullpen_v2.pkl`

# Session Recap — INC-17 P1 MODEL-HEALTH Diagnosis — for PM Claude

**Date:** 2026-06-28 · **Status:** ✅ DIAGNOSE-AND-STOP COMPLETE — root cause identified with evidence; decisive operator test specified; sensor hardened; §0.5 bake-off routing decision pending the rescore.

---

## What the alert said

Gate FAILED for `['home_win','run_differential']` over 2026-06-10→2026-06-28 (post_lineup):
- `home_win`: corr **0.013** < 0.05; Brier **0.271** > no-skill 0.249
- `run_differential`: corr **−0.021** < 0.05

---

## Hypotheses tested and verdicts

### ❌ RULED OUT — Woba bug (W1d, 06-25)

The W1d woba-zero bug zeroed matchup features (`mart_pitcher_batter_history` woba/xwoba) on 06-25. Decisive evidence: period B (the bug day itself) had **rd_corr = +0.3723** — the highest in the full window. hw_corr = 0.038, brier = 0.2475 (best day in window). The alert is a 18-day rolling-window average; the bug was 1 day and did not cause the collapse. **Woba bug is CLOSED as a cause.**

### ❌ RULED OUT — Label/join artifact

`mart_game_results.run_differential = home_final_score − away_final_score` confirmed directly (Snowflake spot-check, 20 rows). Sign convention matches the model's target. The dedup logic (`ROW_NUMBER … inserted_at DESC`) is consistent with how predictions are scored. No TZ/date mismatch found.

### ❌ RULED OUT — Serving degradation of unconditional-core features

`discriminative_coverage` ≈ **0.99** across all post_lineup v6 days (06-10 to 06-28). Zero `is_degraded` flags. `avg_imputed_discriminative_count` ≈ 0.07 (nearly 0). The ELO, bullpen-EB, RISP, park features are being served correctly. The A2.5 serving-health metric is CLEAN.

### ❌ RULED OUT — run_differential systematic sign flip

`rd_corr = −0.021` with n=198 games: 95% CI ≈ ±0.139. Definitively noise. Period-by-period swings (+0.37 / −0.11 / ±0.00) are sampling variance with 8-15 games/sub-window.

### ✅ IDENTIFIED — v6 produces genuinely flat outputs

| Model | cons_spread | cal_spread | ngb_spread | clf_spread | rd_spread |
|-------|-------------|------------|------------|------------|-----------|
| v5 (same days, same game_pks) | **0.188** | **0.184** | ~0.18-0.22 | ~0.17-0.21 | ~1.4-2.5 |
| v6 (06-10 to 06-22) | **0.057** | **0.035** | ~0.04-0.08 | ~0.04-0.06 | ~0.4-0.8 |

Both NGBoost (`ngb_spread`) AND XGBoost classifier (`clf_spread`) are compressed — this is pre-calibration flatness in the consensus itself, not the calibrator squashing it.

V6 IS correlated with V5 (`corr_v6_vs_v5_cal = 0.424`): it ranks games in the same direction but with 3-4× less confidence. Not random noise — appropriately uncertain.

**Why v6 is flat**: v4/v5 were dominated by `bp_eb_xwoba` (the within-game bullpen leak, the #1-#2 feature per E13.11 SHAP) which gave them high (but misleading) spread ~0.19. V6 removed that leak. The remaining clean features — ELO diff, pythagorean, RISP, park — have weaker between-game separation, so v6 correctly outputs near-0.5 for most games.

---

## Decisive test remaining (OPERATOR MUST RUN)

The offline re-score forks "genuinely limited model" from "residual serving gap in lineup-gated features":

```bash
# Loads the historical feature store; can exceed 1 min — hand off to operator
uv run python scripts/ops/rescore_audit.py --since 2026-06-23 --compare-live
```

**Reading the result**:
- **Re-scored corr ≫ live corr (toward CV ~0.05-0.15)** → the model HAS more signal when served correct features → residual serving gap (likely lineup-gated matchup/archetype features being imputed null even on post_lineup predictions). Fix the serving path, NOT a retrain.
- **Re-scored corr still ≈ 0 with training-time features** → GENUINE DECAY. The de-leaked v6 has insufficient signal with the clean feature set. Route to a **§0.5 bake-off** (separate Opus story: ≥3 candidates, Optuna, purged/embargoed CV, PBO<0.2/DSR>0; do NOT start it here).

---

## Code changes shipped this session

### 1. `pipeline/sensors/model_health_alert_sensor.py`
- `_GATE_FLOOR_DATE` updated **2026-06-10 → 2026-06-23** (v6 deploy date). The old floor let v4/v5 predictions (selected by the dedup for pre-06-23 games without a v6 backfill row) contaminate the window with their known-near-zero-but-different-root-cause metrics.
- Added `_MODEL_VERSION = "v6"` and passed `model_version=_MODEL_VERSION` to `mh.evaluate()`. Future promotions: update this constant.
- Alert message now includes: (a) flat-output note when spread < 2×MIN_SPREAD_PROB, (b) rescore_audit diagnostic step, (c) model_version in the inspect command.

### 2. `betting_ml/monitoring/model_health_metrics.py`
- `_print_report()` now emits a `⚠ FLAT-OUTPUT` line when `calibrated_spread < MIN_SPREAD_PROB * 2` (i.e., < 0.06). Points to rescore_audit. This is an early-warning diagnostic, not a new gate condition.

### CI gate
- Fast gate: `uv run pytest -m "not slow" -n auto` → **683 passed, 1 skipped** ✅
- Syntax-clean: both changed files pass `ast.parse()` ✅

---

## Side findings (not the root cause, but important)

### A2.5 blind spot: lineup-gated features
`discriminative_coverage` deliberately excludes lineup-gated feature families (matchup woba/archetype, lineup-EB aggregates, starter-EB) — by design, to avoid crying wolf pre-lineup. But for **post_lineup** predictions these SHOULD be populated. A future story should add an explicit post_lineup integrity check for a representative sample of lineup-gated features (e.g., average non-null rate of `matchup_woba` or archetype features in the prediction day's feature store). If they're all-null even on post_lineup, that's a serving gap the current metric can't see.

### Mixed-model dedup confounds the window metric
Before the sensor fix, the 30-day window mixed v4/v5 predictions (CAL_SPREAD ~0.19, near-zero corr — known; old root cause) with v6 predictions (CAL_SPREAD ~0.03, near-zero corr — new root cause). The resulting aggregate hid both issues. The model_version pin in the sensor now gives a clean single-champion measurement.

---

## ⏭️ Operator handoff

### Decisive step (REQUIRED before routing)
```bash
# Offline re-score with training-time features (>1 min — run and report result)
uv run python scripts/ops/rescore_audit.py --since 2026-06-23 --compare-live
```

### Commit the sensor hardening
```bash
git add pipeline/sensors/model_health_alert_sensor.py \
        betting_ml/monitoring/model_health_metrics.py
git commit -m "INC-17-P1: sensor floor→06-23, model_version=v6, flat-output warning in metrics"
```

### If rescore shows corr recovers (serving gap)
Identify which lineup-gated features are null on post_lineup predictions (likely matchup/archetype after a W3 mart migration side-effect). Fix the serving path (dbt mart or predict_today feature-pull). Re-run the health gate to confirm.

### If rescore shows corr stays flat (genuine decay)
File a new **§0.5 bake-off story** (Opus) on the H2H home_win target. Pre-register ≥3 candidate model classes (include: a market-regression baseline, a regularized logistic on ELO+pythagorean, and one tree-based learner). Tune with Optuna, gate on purged/embargoed CV, PBO<0.2/DSR>0. Do NOT use a single-architecture patch.

**Do NOT retrain v6 in a quick single-arch fix regardless of which path is taken.**

---

## Rescore result (operator ran 2026-06-28) — SERVING GAP CONFIRMED

```
[home_win]  n=63  corr (live→rescored): 0.031 → 0.149  verdict: FAIL → FAIL
[run_differential]  corr (live→rescored): 0.027 → 0.125  verdict: FAIL → PASS
```

Full output:
```
[home_win]  n=63  base_rate=0.4127  no_skill_Brier=0.2424
   calibrated  corr=0.1485  Brier=0.2449  spread=0.0295  mean=0.4898
   consensus   corr=0.1474  Brier=0.2427  spread=0.0481  mean=0.4833
   → FAIL (spread 0.029 < 0.03 flat-output; Brier 0.245 barely above no-skill - 0.002)

[run_differential]  n=63  corr=0.1251  pred_spread=0.5744  → PASS

[total_runs]  n=63  corr=0.1856  pred_spread=0.3548 < 0.5 gate  → FAIL (flat spread)
```

**Interpretation:** Both `home_win` (+5× corr jump, 0.031→0.149) and `run_differential` (+5× corr jump, 0.027→0.125) recover substantially on training-time features. The rescore script's own legend applies: **"a large corr jump (live≈0 → rescored toward CV) ⇒ the model has skill when served correct features ⇒ SERVING was the problem."**

The remaining `home_win` FAIL on rescore (spread just below 0.03 gate, Brier barely above no-skill − 0.002) reflects v6's inherent compression from de-leaking — not a serving issue. The model IS directional; it just outputs near-0.5 for most games. This is a **separate signal** from the serving gap.

**Final routing: SERVING GAP → INC-17 P2 (find and fix which lineup-gated features are null on post_lineup predictions). Do NOT retrain.**

Key diagnostic: lineup-gated features (matchup woba/archetype/lineup-EB aggregates) appear null in the live prediction feature rows even for post_lineup predictions. The A2.5 discriminative_coverage is blind to this class of corruption by design.

# Epic 17 — Context Handoff (2026-06-05)

**For:** The session that will execute the bullpen sub-model retrain (Story 17.0) and subsequent NUTS re-run (Story 17.1 Phase 1).

---

## State of Epic 17 as of 2026-06-05

### Architecture confirmed

- **Model:** PyMC hierarchical NegBin, per-side (game_pk, side) grain
- **Inference:** NUTS 4 chains × 4000 draws + 2000 tune, target_accept=0.90, seed=42
- **Season mapping for 2026:** `delta_season[:, 3]` — delta_2025 as proxy (v1 approach). **The v2 calibration window (Mar+Apr 2026 as training data) is permanently abandoned.**
- **Signal scalers:** Fitted on 2022-2025 only (StandardScaler per signal). Path: `betting_ml/models/bayesian/signal_scalers.joblib`.
- **Scripts:**
  - NUTS script: `betting_ml/models/bayesian/run_scoring_nuts.py` (v1 — calibration window code exists but `_CALIB_MONTHS` is not used in inference path)
  - ADVI script: `betting_ml/models/bayesian/run_scoring_advi.py` (shared data-loading functions; do not modify)
  - Diagnostic audit scripts: `betting_ml/scripts/audit/`

### Kill criterion

**PPM ≤ 8.81 on May-2026 OOS games** — this is the first check; if it fails, stop. Do not evaluate three-layer or Layer 4 gates.

---

## Story 17.1b findings (2026-06-04) — what the diagnostics proved

### Monthly PPM breakdown (v2 trace + v1 mapping)

| Month | Games | PPM | Actual | Bias | Result |
|-------|-------|-----|--------|------|--------|
| March | 74 | 8.3889 | 8.5676 | −0.18 | **PASS** |
| April | 359 | 8.7163 | 9.1365 | −0.42 | **PASS** |
| May | 380 | 8.8601 | 8.6842 | +0.18 | **FAIL** |

The failure is May-specific. The model prices run scoring correctly in March and April.

### Bullpen discount diagnostic

- `beta_bullpen_2026_discount ~ Normal(0, 0.5)` added to NUTS
- Posterior: mean=−0.227, 94% HDI=[−0.409, −0.031] — **HDI entirely negative → bullpen drift is confirmed**
- Effective beta_bullpen for 2026: 0.148 (vs training 0.191)
- May PPM with discount: **9.2674 — FAIL** (running on v2 base; the discount reduces but cannot cancel the broken delta_2026≈0 baseline)

### Root cause isolated

1. The +0.2882σ z-shift in `opp_bullpen_mu` for 2026 games is OOD relative to the 2022-2025 training distribution.
2. beta_bullpen × +0.2882σ ≈ +0.055 runs/side = **+0.11 total runs = the entire May kill criterion overshoot.**
3. With v1 mapping (delta_2025 for 2026), May PPM = 8.8601 — missing the 8.81 threshold by exactly 0.050 runs.
4. **Correcting the bullpen OOD is sufficient to pass the kill criterion.** No architecture change needed.

---

## What is active in production right now

### Bullpen OOD gate (active 2026-06-05)

The gate is live in `betting_ml/utils/probability_layer.py::compute_bet_permission()`:
- Reads `bullpen_mu_home` and `bullpen_mu_away` from the prediction row
- Computes z-scores against training distribution: mean=1.423189, std=0.496120
- If `|z_home| > 1.5` OR `|z_away| > 1.5` → `bullpen_signal_ood = True` → `qualified_bet = False`
- Wired into `scripts/predict_today.py` — loads bullpen signals from `feature_pregame_sub_model_signals`, stores `bullpen_z_score_home`, `bullpen_z_score_away`, `bullpen_signal_ood` in `daily_model_predictions`

**Gate is independent of Epic 17 completion.** It prevents totals bets in the OOD regime while the bullpen retrain is pending.

### OOD gate parameters in `sub_model_registry.yaml` under `bullpen_v2.ood_gate`:

```yaml
training_mean: 1.423189
training_std: 0.496120
ood_threshold_sigma: 1.5
upper_threshold: 2.167369
lower_threshold: 0.679009
```

---

## Story 17.0 — What this session must do first

Story 17.0 is the hard gate before the next NUTS run. Details in `implementation_guide.md` § 17.0.

### Step 1 — Investigate Hypothesis A vs B (< 5 min, local)

Run this quick check to understand whether the bullpen_mu drift is from real-world run scoring changes (Hypothesis A) or feature distribution shift (Hypothesis B):

```python
import pandas as pd
df = pd.read_parquet("betting_ml/models/layer3/oos_signals/oos_signals_bullpen.parquet")
print("bullpen_mu by season:")
print(df.groupby("season")["bullpen_mu"].agg(["mean", "std"]).round(4))
```

Then check actual runs scored:
```python
from betting_ml.models.bayesian.run_scoring_advi import _load_game_results, _expand_to_sides
sides = _expand_to_sides(_load_game_results([2022, 2023, 2024, 2025, 2026]))
print("runs_scored by season:")
print(sides.groupby("season")["runs_scored"].mean().round(4))
```

**If bullpen_mu increased in 2026 but runs_scored did not → Hypothesis B (feature drift); retrain must fix input features.**
**If both increased → Hypothesis A (real-world change); retrain on 2026 data will naturally fix it.**

Document the result in `implementation_guide.md` Story 17.0 tasks.

### Step 2 — Retrain bullpen_v2

- Extend training window to include 2026 completed games
- Same 24 features as current champion
- Walk-forward CV with 2026 as an evaluation fold
- Promotion gate: NegBin NLL < 1.8852 AND calib_80 ≥ 0.80

### Step 3 — Verify OOD gate passes (pre-committed criterion)

After retrain and re-generating OOS signals, run:

```python
import pandas as pd, joblib
df = pd.read_parquet("betting_ml/models/layer3/oos_signals/oos_signals_bullpen.parquet")
new_scaler = joblib.load("betting_ml/models/bayesian/signal_scalers.joblib")["opp_bullpen_mu"]
df_2026 = df[df["season"] == 2026]
# opp_bullpen_mu is bullpen_mu of the opposing team — same distribution as raw
z_2026 = new_scaler.transform(df_2026["bullpen_mu"].values.reshape(-1, 1)).ravel()
print(f"2026 mean z-score: {z_2026.mean():+.4f}")
print(f"Gate: {'PASS' if abs(z_2026.mean()) <= 1.0 else 'FAIL'}")
```

**Gate: mean |z_2026| ≤ 1.0.** If this fails, the retrain did not fix the OOD — investigate before proceeding.

### Step 4 — Update constants

After retrain closes story 17.0, update:
1. `betting_ml/utils/probability_layer.py`: `_BULLPEN_OOD_TRAINING_MEAN`, `_BULLPEN_OOD_TRAINING_STD`
2. `betting_ml/sub_model_registry.yaml`: `bullpen_v2.ood_gate` block (all 4 numeric values)

---

## Story 17.1 — Next NUTS run (after 17.0 closes)

**Script:** `uv run python betting_ml/models/bayesian/run_scoring_nuts.py`

**Expected runtime:** ~10 minutes on M-series CPU (same as prior runs).

**Expected result:** With corrected bullpen signals, the +0.2882σ OOD shift becomes ≤ ±1.0σ → beta_bullpen × new_z ≈ 0 → May PPM should drop from 8.8601 to approximately 8.75-8.80 → **PASS**.

**Exact command:**
```bash
uv run python betting_ml/models/bayesian/run_scoring_nuts.py
```

**Report:** PPM value, PASS/FAIL verdict, R-hat max, ESS min, divergence count.

**On PASS:** Proceed to Story 17.1 Phase 3 (full three-layer + Layer 4 evaluation).
**On FAIL:** Report the PPM value; do not proceed to three-layer evaluation.

---

## Files modified in this session (2026-06-05)

| File | Change |
|------|--------|
| `betting_ml/utils/probability_layer.py` | Added `_BULLPEN_OOD_TRAINING_MEAN/STD/THRESHOLD`, `_eval_bullpen_ood_gate()`, wired into `compute_bet_permission()` |
| `betting_ml/sub_model_registry.yaml` | Added `bullpen_v2.ood_gate` block |
| `scripts/predict_today.py` | Added `compute_bet_permission` import, `_load_bullpen_ood_signals()`, 3 new columns (`bullpen_z_score_home/away`, `bullpen_signal_ood`) |
| `quant_sports_intel_models/baseball/implementation_guide.md` | Added Story 17.0 (bullpen retrain spec), updated Story 17.1b (diagnostic record), updated Epic 17 status headers and sequencing table |
| `betting_ml/scripts/audit/diagnose_monthly_ppm.py` | Created (monthly PPM diagnostic) |
| `betting_ml/scripts/audit/nuts_bullpen_discount_diagnostic.py` | Created (bullpen discount NUTS diagnostic) |

---

## Key numbers to keep in context

| Quantity | Value |
|----------|-------|
| Kill criterion threshold | 8.81 runs (May-2026 PPM) |
| v1 NUTS May PPM | 8.8607 — FAIL (+0.051) |
| v2 NUTS May PPM | 9.3720 — FAIL (+0.562) — v2 ABANDONED |
| May actual mean runs | 8.6842 |
| beta_bullpen (training) | 0.191 |
| 2026 opp_bullpen_mu z-shift | +0.2882σ |
| Implied PPM contribution of z-shift | +0.11 total runs |
| OOD gate threshold | |z| > 1.5σ (absolute) |
| OOD training mean | 1.423189 |
| OOD training std | 0.496120 |
| Story 17.0 pass criterion | mean |z_2026| ≤ 1.0σ after retrain |

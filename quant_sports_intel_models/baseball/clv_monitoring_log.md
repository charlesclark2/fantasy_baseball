# CLV Monitoring Log

Append-only log of model ablation and CLV results.

---

## 6D.5 EB Ablation — distributional NegBin (20260601T053223)

| Metric | Champion (EB, 24 feat) | No-EB (21 feat) | Delta |
|--------|------------------------|-----------------|-------|
| CV NLL | 2.05044 | 2.1409 | +0.0904 |
| calib_80 | 0.8484200000000002 | 0.8173 | -0.0312 |
| High-fatigue NLL | 1.877 | 1.7788 | -0.0982 |

**Decision:** RETAIN  
**Rationale:** EB reduces CV NLL by 0.0904 (>= 0.005 threshold)  
**File:** `betting_ml/models/sub_models/bullpen_v2/ablation_eb_bullpen_20260601T053223.json`  

---


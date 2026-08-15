# E1.13 — seasonnorm-cure retrain-vs-incumbent (total_runs/pre_lineup)

*Generated 2026-08-15T00:45:18.581801+00:00*

**VERDICT: INCUMBENT_STANDS**  (contest: TIES; default was INCUMBENT_STANDS; `best_alpha=0` — no edge claim either way)

- window 2021+ · 12,078 rows · 3 purged folds (embargo 3d)
- exposure: cure touches 180 rows (1.49%); touched EVAL rows 71
- CRPS margin (incumbent_asfit − refit_cured): **+0.00068** vs noise floor 0.02
- DSR (fixed convention) 0.659 vs bar 0.95 · PBO UNDEFINED
- PIT-KS incumbent_asfit 0.0765 · refit_cured 0.076 (tol 0.0077; ok=True)
- input-shift cost (same fit, pre-cure vs cured eval): mean |ΔCRPS| 0.00292
- touched-rows paired delta: 0.09085

Per fold:

| fold | eval year | n | touched | incumbent_asfit | refit_cured | incumbent on pre-cure |
|---|---|---|---|---|---|---|
| 0 | 2024 | 2146 | 26 | 2.4193 | 2.4198 | 2.4187 |
| 1 | 2025 | 2025 | 24 | 2.5808 | 2.5790 | 2.5771 |
| 2 | 2026 | 1517 | 21 | 2.5128 | 2.5119 | 2.5120 |

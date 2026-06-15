# Story 30.9 — Learned h2h ensemble stack vs 50/50 blend

**Decision:** PROMOTE  (best variant: convex_w, pooled Δbrier=-0.0037)

⚠ **SHELVED regardless of verdict** — `best_alpha=0.0` makes the live posterior pure market, so the blend weight has no live bet payoff until the Story 30.6 alpha-unlock.

## Status quo — does 50/50 beat its best component?

| season | 50/50 Brier | clf-only Brier | run_diff-only Brier | 50/50 NLL | 50/50 AUC |
|---|---|---|---|---|---|
| 2024 | 0.1954 | 0.1930 | 0.2037 | 0.5752 | 0.7728 |
| 2025 | 0.1953 | 0.1914 | 0.2048 | 0.5756 | 0.7709 |
| 2026 | 0.2019 | 0.2027 | 0.2050 | 0.5899 | 0.7577 |
| pooled | 0.1964 | 0.1939 | 0.2044 | 0.5777 | 0.7696 |

## Stack gate

- variant pooled Brier: `{'convex_w': 0.19461551673302926, 'logistic': 0.19504012701835485}`
- eval seasons: completed=[2025], current=2026
- params (last fold): `{'convex_w_on_clf': 1.0, 'logistic_coef': [4.0863026887366765, 0.9092159396343534], 'logistic_intercept': -2.4738165646945105}`

- Pooled improvement -0.0037 clears the 0.002 noise floor.
- Paired bootstrap 95% CI upper bound -0.0020 < 0 (significant).
- No completed season regresses beyond tolerance (cross-season consistent).
- Current season 2026 corroborates (+0.0009).
- Single-eval criteria PASS → PROMOTE candidate. Confirm hysteresis (≥2 consecutive passes) before deploy.

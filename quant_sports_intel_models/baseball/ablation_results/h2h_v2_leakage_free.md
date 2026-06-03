# H2H Approach B — Leakage-Free Re-Evaluation (Phase 2b)

_Story 11.3 re-run on the leakage-free walk-forward Layer 3 matrix (`build_oos_matrix`, OOS sub-model signals from Phase 1). Same classifier machinery as the contaminated run — only feature provenance changed._

- Coverage seasons: [2022, 2023, 2024, 2025, 2026] (run_env 2021 floor → first eval fold 2024 at min_train_seasons=2).
- Dataset: X=(9428, 38) after dropping the 6 all-NaN matchup columns (not regenerated in Phase 1); base_rate 0.5297; market coverage 7084/9428.
- Winner (lower CV log-loss): **lightgbm** (A1 elasticnet ll=0.6359 / A2 lightgbm ll=0.6193).

## Honest per-season head-to-head (identical market-covered games)

| season | n (cov) | model Brier | market Brier | Δ (mkt−mdl) | market quality | beats credible mkt |
|---|---|---|---|---|---|---|
| 2024 | 1621 | 0.2142 | 0.2405 | +0.0263 | ⚠️ degraded | — |
| 2025 | 1659 | 0.2069 | 0.2435 | +0.0366 | ⚠️ degraded | — |
| 2026 | 628 | 0.2239 | 0.1797 | −0.0442 | credible | ❌ |

> **Market-baseline quality gate:** a credible sharp h2h market scores Brier ≈0.20-0.22 (a 0.235 threshold; coin flip at the 0.53 base rate ≈0.249). Seasons flagged ⚠️ degraded (2024, 2025) have near-flat/stale lines — the historical Odds-API Bovada h2h snapshots (avg pred ≈0.53, barely deviating from base rate). A "win" against those reflects a broken baseline, not skill, so they are EXCLUDED from the verdict. Confirmed via direct per-season/per-source market Brier (2026-06-03): 2024 bovada-source Brier 0.2400 (n=1782), 2025 0.2427 (n=1843), 2026 0.1978 (n=822) — and 2024/25 are ~99% bovada-source, so this is line quality, not a consensus-fallback artifact.

## Verdict

- **Leakage fix confirmed:** model Brier is stable across seasons (2024=0.214, 2025=0.207, 2026=0.224) — no 2026 collapse. This is the honest-OOS signature we were after; the contaminated run's implausible 2023-25 ~0.185 Briers are gone.
- **Credible-baseline seasons:** [2026]. Model beats the credible market in: **none**.
- **Bottom line: NO EDGE.** On the only credible market season (2026), the market beats the model (model 0.224 vs Bovada ~0.18-0.20). The 2024-25 "wins" are artifacts of degraded historical lines. This is the honest 11.4/11.7 bar — the direct H2H classifier does not beat Bovada.

## Implication for Epic 11

11.3 Approach B is **not promotable** on this evidence. The contaminated headline (CV Brier 0.1943 "beats" market) was leakage; with leakage removed and the baseline quality-gated, there is no edge. 11.4 (champion select) / 11.7 (gate) should treat H2H as "no demonstrated edge vs Bovada" until a credible-market, leakage-free season shows otherwise. The 2024-25 Bovada h2h line-quality problem also caps any historical H2H backtest — only 2026 (Parlay API) is a trustworthy market baseline.

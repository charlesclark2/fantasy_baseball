# Layer 3 Signal Promotion Log (Epic 9, Story 9.5)

Durable audit of each sub-model signal group's Layer 3 evaluation. Source of
truth for the verdicts wired into `sub_model_registry.yaml`, the stacking weights
in `betting_ml/models/layer3/stacking_weights.json` (Story 9.3), and the feature
contract `betting_ml/models/layer3/layer3_feature_columns.json` (Story 9.4).

- **Evaluation:** Story 9.2 — `betting_ml/scripts/evaluate_layer3_signals.py`, walk-forward CV (4 season folds: 2023–2026), groups added incrementally.
- **Eval artifact:** `ablation_results/layer3_signal_evaluation_20260602_151859.json` (+ `.md`)
- **MLflow experiment:** `layer3_evaluation` (run ID not persisted in the artifact; the JSON above is the canonical record).
- **Matrix:** 11,661 games, 2021-01-01 onward (`load_layer3_features`).
- **Gates:** `total_runs` — held-out NLL delta ≤ **−0.005**; `home_win` — held-out Brier delta ≤ **−0.001**; consistency ≥ **⌈0.6·n_folds⌉ = 3 of 4** folds improved. Verdicts: **promote** (clears gate + consistency), **defer** (directional but below gate / overlaps a promoted signal), **reject** (no effect / wrong direction).

## Summary

| Signal group | Champion | `total_runs` | `home_win` | Stacking weight (totals / h2h) |
|---|---|---|---|---|
| run_env | `run_env_v4` | **promote** (NLL −0.0137, 4/4) | defer (Brier −0.0003, 3/4) | 0.331 / — |
| offense | `offense_v2` | **promote** (NLL −0.0117, 3/4) | **promote** (Brier −0.0133, 3/4) | 0.332 / 0.493 |
| starter | `starter_v1` | defer (NLL −0.0026, 4/4) | defer (Brier −0.0007, 4/4) | — / — |
| starter_ip | `starter_ip_v1` | defer (NLL −0.0010, 3/4) | defer (Brier −0.0009, 4/4) | — / — |
| bullpen | `bullpen_v2` | **promote** (NLL −0.0292, 4/4) | **promote** (Brier −0.0266, 4/4) | 0.337 / 0.507 |
| matchup | `matchup_v1` | defer (NLL −0.0010, 3/4) | **reject** (Brier +0.000007, 0/4) | — / — |

Promoted: **3 of 6** groups on totals (run_env, offense, bullpen), **2 of 6** on home_win (offense, bullpen). The foundational gate — `run_env_v4` and `offense_v2` both clearing on `total_runs` — passes, so Epic 10 is unblocked.

---

## run_env (`run_env_v4`)

| Target | Verdict | Mean Δ | Fold wins | Wilcoxon p | Calibration | Coverage-conditional (available) |
|---|---|---|---|---|---|---|
| `total_runs` | **promote** | −0.013689 NLL | 4/4 | 0.125 | 0.836 (not miscalibrated) | n=7,269, NLL Δ −0.01449 |
| `home_win` | defer | −0.000251 Brier | 3/4 | 0.625 | 0.836 | — |

**Rationale.** run_env clears the totals gate cleanly — every fold improves and the effect is the second-largest of the promoted set, with a healthy 80% PI calibration of 0.836. It defers on home_win because its −0.00025 Brier delta is well below the −0.001 gate: run_env predicts the *scoring environment* (park/weather/umpire → total runs), not directly which side wins, so its head-to-head contribution is marginal in isolation.

**Re-evaluation trigger (home_win).** Re-evaluate once **Epic 11 Story 11.2 (Approach B)** derives win probability from Epic 10's per-side NegBin run distributions — run_env enters win prob *indirectly* through the totals model there, which is the right pathway for an environment signal. Otherwise, revisit if a future `run_env` version shows standalone home_win Brier ≤ −0.001.

---

## offense (`offense_v2`)

| Target | Verdict | Mean Δ | Fold wins | Wilcoxon p | Calibration | Coverage-conditional (available) |
|---|---|---|---|---|---|---|
| `total_runs` | **promote** | −0.011749 NLL | 3/4 | 0.25 | 0.829 (not miscalibrated) | n=7,269, NLL Δ −0.01675 |
| `home_win` | **promote** | −0.013349 Brier | 3/4 | 0.25 | 0.829 | — |

**Rationale.** offense is a foundational distributional signal and the only group promoted on both targets besides bullpen. It clears both gates with 3/4 consistency; the lone miss is the 2026 fold (partial in-season data, slight regression to +0.012 NLL / +0.001 Brier), while the trailing three seasons are strongly negative (totals down to −0.026 in 2025). Calibration 0.829 is healthy.

**No re-evaluation trigger** — promoted on both targets.

---

## starter (`starter_v1`)

| Target | Verdict | Mean Δ | Fold wins | Wilcoxon p | Calibration | Coverage-conditional |
|---|---|---|---|---|---|---|
| `total_runs` | defer | −0.002587 NLL | 4/4 | 0.125 | latent¹ | avail n=7,260 Δ −0.00261; unavail n=9 Δ −0.00825 |
| `home_win` | defer | −0.000697 Brier | 4/4 | 0.125 | latent¹ | — |

**Rationale.** starter is *directionally* helpful in every fold (4/4 on both targets) but its magnitude sits below both gates (−0.0026 totals, −0.0007 home_win). Most of its predictive content overlaps the promoted run_env + bullpen signals once those are already in the model, so it adds little incremental value at this stage.

**Re-evaluation trigger.** Re-evaluate when **(a)** the Epic 5D distributional starter retrofit ships a calibrated `(mu, sigma)` starter signal, **or (b)** Epic 10's totals-champion feature attribution shows residual standalone starter signal beyond run_env + offense + bullpen.

---

## starter_ip (`starter_ip_v1`)

| Target | Verdict | Mean Δ | Fold wins | Wilcoxon p | Calibration | Coverage-conditional |
|---|---|---|---|---|---|---|
| `total_runs` | defer | −0.000967 NLL | 3/4 | 0.625 | latent¹ | avail n=7,134 Δ −0.00155; unavail n=135 Δ −0.00042 |
| `home_win` | defer | −0.000902 Brier | 4/4 | 0.125 | latent¹ | — |

**Rationale.** starter_ip has the smallest totals effect of any group (−0.0010, 3/4, Wilcoxon p=0.625 — not significant). Its value is expected to surface through *interaction* with the bullpen signal (a short starter forces bullpen exposure), not as a standalone term, which is why it defers rather than promotes.

**Re-evaluation trigger.** Re-evaluate after **Epic 6D Candidate B** wires `starter_ip_p20_outs` (pessimistic depth) into the bullpen exposure model — the integrated path is where starter depth is expected to pay off.

---

## bullpen (`bullpen_v2`)

| Target | Verdict | Mean Δ | Fold wins | Wilcoxon p | Calibration | Coverage-conditional |
|---|---|---|---|---|---|---|
| `total_runs` | **promote** | −0.029174 NLL | 4/4 | 0.125 | latent¹ | avail n=7,125 Δ −0.03228; unavail n=144 Δ **+0.011** |
| `home_win` | **promote** | −0.026583 Brier | 4/4 | 0.125 | latent¹ | — |

**Rationale.** bullpen is the strongest signal in the set on both targets — the largest mean delta, 4/4 folds, and monotone improvement across seasons. The coverage-conditional split is informative: on the 144 games where bullpen is *unavailable*, the totals NLL delta is **+0.011** (slightly worse), as expected for early-season games with thin bullpen history — the Story 9.4 completeness floor (≥0.40) and `low_confidence` flag handle those at inference.

**No re-evaluation trigger** — promoted on both targets. Carries the largest stacking weight (0.337 totals, 0.507 h2h).

---

## matchup (`matchup_v1`)

| Target | Verdict | Mean Δ | Fold wins | Wilcoxon p | Calibration | Coverage-conditional |
|---|---|---|---|---|---|---|
| `total_runs` | defer | −0.000972 NLL | 3/4 | 0.625 | latent¹ | avail n=6,927 Δ −0.00162; unavail n=342 Δ −0.00283 |
| `home_win` | **reject** | +0.000007 Brier | 0/4 | 0.125 | latent¹ | — |

**Rationale.** matchup defers on totals (−0.0010, marginal, p=0.625) and is **rejected** on home_win, where its mean delta is +0.000007 across 0/4 winning folds — effectively no effect. The matchup model currently trains on only 125 archetype-cell rows (batter_cluster × pitcher_cluster × season) and its advantage signal is near-constant at this maturity, so it carries no head-to-head information yet.

**Re-evaluation triggers.**
- `total_runs` (defer): re-evaluate once the Epic 8 champion has **≥ 50 games of sequential posterior updates** in `matchup_cell_sequential_posteriors` (enough cell history to move the advantage signal off its prior).
- `home_win` (reject): re-evaluate **only after a material Epic 8 architecture change** — e.g., soft-assignment expansion or a finer archetype-cell grid that gives the signal real variance.

---

¹ **latent / out-of-matrix calibration:** `uncertainty_calibration_score` is reported only for groups whose target is directly observable in the Layer 3 matrix (run_env, offense → 0.836 / 0.829). starter, starter_ip, bullpen, and matchup predict latent quantities (suppression residual, innings depth, bullpen quality, archetype advantage) whose `(mu, sigma)` calibration is gated at *training time* in their source epics (5 / 5D / 6D / 8), not re-derivable from the totals/home_win matrix — so the score is `null` here by design, not a gap.

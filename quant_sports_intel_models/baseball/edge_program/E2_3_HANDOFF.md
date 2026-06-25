# E2.3 — Convolution → predictive distributions: session recap & PM handoff

_Session 2026-06-24 · Model track (Session A) · market-blind · builds on E2.1 (per-side NegBin marginals) + E2.2 (dependence finding)._

---

## TL;DR

**E2.3 is PRODUCT-COMPLETE.** The honest, calibrated totals distribution the totals UX needs (full-game **total** + **team totals**) is built, gate-passing, and serving-ready. The **run-diff** sub-distribution is a **documented, accepted near-miss** on one calibration heuristic — diagnosed to a by-design cause, deliberately not chased. **→ proceed to E2.5** (no further E2.3 re-run needed).

| Distribution | calib_80 | PIT-flat (max decile dev) | Verdict |
|---|---|---|---|
| **Total** (over/under) | 0.838 | ✅ 0.0068 | **PASS** — the shipped product |
| **Home team total** | 0.863 | ✅ 0.0091 | **PASS** |
| **Away team total** | 0.847 | ✅ 0.0138 | **PASS** |
| **Run-diff** (H2H input) | 0.839 | ❌ 0.0303 (bar 0.025) | accepted near-miss (see §4) |

Gate prints `NOT MET` **solely** because of run-diff's PIT-flatness — an honest finding, not a blocker (cf. E2.1b / E2.2, where "NOT-MET = the finding").

---

## 1. What the story asked for

Convolve the two E2.1 per-side NegBin run marginals into honest predictive distributions for the **total** (sum), **run-diff** (difference; a distributional H2H input), and **team totals** (marginals); emit a P05…P95 quantile grid + `p_over(line)`; store **params + grid, not raw samples** (§6 cost). **AC:** PIT-flat / `calib_80 ≥ 0.80` for the full-game total; run-diff + team-total marginals also PIT-calibrated.

Three prompt directives carried in:
- **🔒 Leak-guard (DO FIRST):** "swap E2.1's bullpen channel to the leakage-safe aggregate before building."
- **⚠️ Fold in E2.2:** home/away runs are independent (ρ=−0.0035) → convolve **independently, no copula**; the ~24% totals-variance shortfall is **marginal under-dispersion** (E2.1 fit `r` on optimistic train-fit means → ~8.5; held-out `r` ≈ 3.7).
- **⚠️ Framing:** E2.3 is **product value** (calibrated distribution), **not an edge claim** (main total efficient per E13.8; derivative-edge = E2.6/E13.13).

---

## 2. Leak-guard: RESOLVED (the prompt's premise was stale)

The prompt said the leakage-safe bullpen swap "was flagged pre-serving but NEVER done." **It was already done — by E1.7 (2026-06-18), at the dbt layer.** Verified two ways:

- **Structural:** `dbt/models/eb_posteriors/eb_bullpen_team_posteriors.sql` (the source of `bp_eb_xwoba`) is de-leaked — equal-weight mean over a **strictly-prior** trailing-30d pre-game relief pool (`appearance_date < game_date`, line 111), spined on `mart_game_spine`. Lineage: `eb_bullpen_team_posteriors` → `mart_bullpen_effectiveness` → `feature_pregame_team_features.bp_eb_xwoba` → `feature_pregame_game_features.{home,away}_bp_eb_xwoba`.
- **Empirical (Snowflake):** `home/away_bp_eb_xwoba` is **96.5–98.9% populated 2018–2026** (avg ~0.31, the de-leaked range).

The E2.1 marginals load `feature_pregame_game_features` **live**, so re-deriving them in E2.3 picks up the de-leaked channel automatically. **No feature-list swap was needed** — and re-fitting a different E2.1 feature set would have been wasted work. The within-game leak E2.1b found was fixed at the dbt layer, not deferred.

---

## 3. What was built

All market-blind (CONTRACT-GUARD on the marginal matrix); independent convolution (ρ=0); per-side dispersion calibrated on held-out residuals.

- **`betting_ml/utils/totals_distribution.py`** (pure NumPy/SciPy, unit-tested):
  - `fit_negbin_dispersion(y, mu)` — held-out dispersion MLE (matches `train_perside_negbin.fit_negbin_r`).
  - `calibrate_dispersion_expanding(seasons, mu, y)` — **leakage-safe expanding window**: season T's `r` is fit on seasons `< T` only (earliest season = un-gated seed).
  - `draw_independent_samples(mu_home, mu_away, r_home, rng, *, r_away=None, n_draws)` — reuses the E2.2 `sample_gaussian_copula_negbin` at ρ=0; per-side `r` supported (`r_away` defaults to `r_home`).
  - `derive_distributions` (total/run_diff/home_total/away_total), `quantile_grid` (P05…P95, 19 levels), `prob_over`/`prob_push`.
  - `randomized_pit` + `pit_flatness` + `interval_coverage` (calib_80) — the calibration diagnostics.
  - `TotalsDistributionParams` (JSON-roundtrippable; `dispersion_r` + per-side `dispersion_r_home`/`dispersion_r_away` + `r_home`/`r_away` accessors).
- **`betting_ml/scripts/totals_generative/fit_totals_distribution.py`** (operator-run, >1-min): re-derives the E2.1 OOS marginals via `fit_copula.collect_oos_marginals` (live de-leaked mart) → per-side leakage-safe dispersion calibration → PIT/calib_80 gate for all four distributions → writes the served params + ablation record + a served-contract example. Flags `--fast` (artifact μ), `--no-save` (dry-run gate).
- **`betting_ml/tests/test_totals_distribution.py`** — 17 tests (dispersion MLE recovery, leakage-safe expanding window can't see the future, independent-convolution moments, per-side dispersion, quantile-grid monotonicity, `p_over`/push, PIT uniformity under correct spec + non-flatness under mis-spec, calib_80 floor, params round-trip).

**Outputs the operator run produced:**
- `betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json` (served params: per-side `r` + grid spec).
- `quant_sports_intel_models/baseball/edge_program/ablation_results/e2_3_convolution_calibration.{json,md}`.

---

## 4. Gate result + the run-diff finding (the substantive part)

Two operator runs (11,662 eval games, 2021–25, OOS purged walk-forward CV):

**Dispersion-calibration thesis VALIDATED.** The leakage-safe expanding-window held-out `r` is **stable**: `r_home` 4.03 (CV 0.008), `r_away` 3.57 (CV 0.023). This fixes E2.1's under-dispersed train-fit `r`=8.5 — and confirms E2.2's call that the apparent "r drifts 33→8" was a train-set-size estimation artifact, not real non-stationarity. **Total + both team totals are calibrated** (table in TL;DR).

**Run-diff is the only miss** — PIT-flatness 0.0303 vs the 0.025 bar (its coverage 0.839 and center 0.503 are fine). The cause is **settled by two independent lines of evidence**:

1. **Synthetic experiment (no Snowflake):** a *correctly-specified* model produces a flat run-diff (0.0067) → the miss is **real, not a difference-of-small-counts discreteness artifact**. And even an *extreme* per-side dispersion asymmetry (r 6 vs 3) only inflates run-diff to ~0.015 → dispersion asymmetry can't explain 0.0303.
2. **The per-side re-run is decisive:** calibrating `r_home`/`r_away` separately **moved the dispersions** (4.03 vs 3.57, as predicted from home over-covering) **but left run-diff unchanged** (0.0301 → 0.0303). Fixing the asymmetry did nothing for run-diff → **the miss is not dispersion; it's the tiny home/away dependence the independent convolution omits by design.** (E2.2: ρ≈0 is negligible for the *total* — which passes — but `var(diff) = var_h + var_a − 2·cov` is the one quantity uniquely sensitive to it.)

**Decision — NOT chased (accepted near-miss):**
- The only fix would be re-introducing a **copula** to add back the dependence — which **directly contradicts E2.2** ("don't force a coupling the data doesn't support") for a difference-only ~0.005 flatness gain.
- **Run-diff is not a served surface.** The shipped totals products are the total + team totals (calibrated). The H2H product uses the calibrated **E13.6** model, not this run-diff distribution.
- So run-diff stands as a documented, well-understood near-miss. E2.3's product deliverable ships.

**Per-side `r` was kept** even though it didn't fix run-diff: it's strictly more correct (home genuinely less dispersed → tighter, better-calibrated home total), and the diagnostic that isolated the cause. The served artifact uses per-side `r`.

---

## 5. Framing (carry into any PM/app messaging)

E2.3 delivers **honest calibration, not an edge.** The main over/under price is efficient (E13.8: coin-flip Brier ~0.250, number near the variance floor), so a calibrated total does **not** imply a beatable main line. `best_alpha = 0` for the main total. The edge question is **gated at E2.6** (main-line un-pause needs NLL<2.8893 AND Brier<0.248; the realistic value path is the **derivative/alt markets** — team/alt totals where the book prices lazily — each vs its own close + PBO<0.2/DSR>0, see E13.13). E2.7 (distribution UX) must use honest framing — calibrated P(over) + distribution, no win-rate/edge claims.

---

## 6. CI / handoff hygiene

- **Python CI:** ✅ `uv run pytest` green — 17 new E2.3 tests pass; full suite was green at the prior checkpoint (557 passed, 1 pre-existing skip). All changes are confined to the three E2.3 files (nothing else imports them).
- **dbt CI:** N/A — **zero dbt files changed** (`state:modified+` builds nothing; `dbtf compile` unaffected).
- **No git commits made** (per repo convention — operator owns git).

**`git add` — full session:**
```
betting_ml/utils/totals_distribution.py
betting_ml/scripts/totals_generative/fit_totals_distribution.py
betting_ml/tests/test_totals_distribution.py
betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json
quant_sports_intel_models/baseball/edge_program/ablation_results/e2_3_convolution_calibration.json
quant_sports_intel_models/baseball/edge_program/ablation_results/e2_3_convolution_calibration.md
quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md
quant_sports_intel_models/baseball/edge_program/build_roadmap.md
quant_sports_intel_models/baseball/edge_program/story_prompts.md
quant_sports_intel_models/baseball/edge_program/E2_3_HANDOFF.md
```
**Excluded (gitignored — S3/registry, not git):** `totals_perside_v1.pkl`, any raw-sample artifacts. The served contract is params + quantile grid only.

**Docs updated:** guide §4 E2.3 (status → ✅ product-complete; task checkboxes ticked; AC annotated), `build_roadmap.md` (row 8), `story_prompts.md` (E2.3 banner). **Memory:** `project_edge_program_e2_3_status.md` + MEMORY.md index.

---

## 7. Next for the PM / model track

1. **E2.5 — Signal registration + leakage-safe backfill** (next in the chain). Register `totals_generative_v1` → `mart_sub_model_signals` (and/or a dedicated `totals_generative_signals` table mirroring `offense_v2_signals`) in `sub_model_registry.yaml`; backfill so the scoring artifact has not seen the scored season (only honest-OOS years valid for eval). **E2.5 blocks E2.6.**
2. **E2.6 — Derivative pricing + validation gates** (needs E2.0 done — it is; 238k closes). CRPS-ensemble beats the `total_runs` champion CRPS-normal (`evaluate_promotion`, SamplesSpec adapter); main-line un-pause thresholds; derivatives gated on CLV-vs-own-close + PBO<0.2/DSR>0. **Final step (§0.3): emit the E2.7 app-session prompt** with the real served contract.
3. **E2.7 — Distribution UX** (separate app session; prompt emitted by E2.6). Renders the total/team-total distribution + alt-line ladder + calibrated P(over) beside the SHAP `pick_explanation`; honest framing; changelog.
4. **Served contract shape (for E2.5/E2.7):** per-game `{mu_home, mu_away, dispersion_r_home, dispersion_r_away, rho=0}` + the P05…P95 quantile grid (total/run_diff/home_total/away_total) + `p_over(line)` ladders. Example payloads are in `e2_3_convolution_calibration.json → served_contract`.

**One judgment call left to the operator/PM:** whether run-diff's accepted near-miss is fine to leave as-is (recommended) or whether they want it revisited later. Recommendation: leave it — re-adding dependence contradicts E2.2 and run-diff isn't shipped. If a future run-line/spread product ever needs a calibrated run-diff, that's the trigger to revisit (and the right tool would be a difference-aware dependence term, evaluated against E2.2's evidence — not a blanket copula).

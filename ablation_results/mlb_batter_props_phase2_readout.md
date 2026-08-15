# MLB Batter Props Phase 2 — readout (hand-authored companion to the generated report)

*2026-08-14 · session `mlb-batter-props-2` · `best_alpha = 0` — no edge / ROI / win-rate claim;
market-blind (book prices never features); deploy-held, research-only, no serving change.*

Generated artifacts: `mlb_batter_props_phase2_bakeoff.md` / `.json` (harness
`betting_ml/scripts/batter_props_phase2_bakeoff.py`, seed 20260814, full run ~140 s laptop).
Pre-registration executed as written:
`quant_sports_intel_models/baseball/edge_program/MLB_batter_props_phase2_preregistration.md`.
Field: 5 real arms (`glm_poisson` = direct-learned foil, `glm_nb`, `hurdle_nb`, `lgbm_nb`,
`pa_structural`) + 2 forward-declared DSR-CONV degenerates; 6 registered half-season folds
(hard data ceiling); exact discrete CRPS primary.

## Verdicts

| leg | bake-off verdict | vs the de-vigged market benchmark |
|---|---|---|
| **total_bases** | **SHIP_CANDIDATE (research-only, deploy-held)** — `glm_nb` beats the foil 6/6 folds, mean CRPS 0.8631 vs 0.9026 (−4.4%), PBO 0.0 (flip mass 20/20 on the winner), DSR 0.9993 ≥ 0.95, p ≈ 0, BH-pass | model Brier better than the market in **6/6 folds** (pooled 0.2400 vs 0.2429) |
| **hits** | **NULL — GENUINE_ABSENCE** (no arm beats the Poisson foil; every alternative class loses or collapses onto it) | model (= the foil) Brier better than the market in **6/6 folds** (pooled 0.2326 vs 0.2388) |
| **home_runs** | **NULL — tie with the foil** (recorded GENUINE_ABSENCE; the nominal `glm_nb` "lead" is ~1e-6 CRPS = a numerical tie, see below) | per-fold ONLY (§9.1): model Brier better in 3 of 6 evaluated folds, worse in 2023H2/2026H1; 2026H1 benchmark is Pinnacle-only (20.4% coverage — a different estimand) |

**Program-level summary:** the candidate-class search is essentially closed — the honest,
registered outcome (§8: "the market is a strong benchmark; the publishable result is a
calibration characterisation") is what happened on hits/HR, while TB is the one leg where a
mechanism (NB dispersion) genuinely earns its place. Separately from the bake-off, the
market-blind model **prices better-calibrated than the de-vigged consensus on hits and TB in
every fold** — which was the registered honest target. That is a calibration statement, not an
edge claim: `best_alpha = 0`, and no bet, ROI, or win-rate figure exists or may be derived
from this work.

## The five reads that matter

1. **TB is a DISPERSION win, attributable via the matched pair (NF-D10 g).** The
   `glm_nb − glm_poisson` paired delta is +0.036..+0.043 CRPS in all 6 folds (same mean model —
   only the NB2 dispersion differs). TB conditional variance is genuinely super-Poisson
   (marginal 1.77² vs mean 1.44); the Poisson foil's PIT max-decile deviation 0.070 vs the
   winner's 0.011. The zero-hurdle mechanism HURTS everywhere it was tried (hurdle − nb
   negative all folds, all legs) — the NB zero mass already prices the zeros.

2. **The HR "win" is a tie, and the mechanism is a collapse (NF1.8 / NF-W2e three-way read).**
   On hits and HR the fitted NB dispersion α hits its floor, so `glm_nb` collapses onto the
   Poisson foil by construction — per-fold skill `[0.0, −0.0, 0.0, …]`, mean delta ~1e-6 CRPS.
   The harness now names this `tie_with_foil` and refuses to classify it as a win (first cut
   produced `DSR_UNREACHABLE` with a misleading "lower-variance design" remedy for what is
   really "the dispersion mechanism has nothing to act on here"). Conditional on the features,
   hits/HR counts are ~equidispersed: dispersion, zero-inflation, boosting, and the structural
   decomposition ALL fail to beat a plain Poisson GLM. Do not re-test candidate classes on
   hits/HR; the open lever (if any) is features, not model class — and E1.11/E13.4's exhausted
   feature ledger for the game models tempers even that.

3. **The NF-D11 MAE inversion fired exactly where registered — measured, not predicted.** On HR
   (88.4% zeros, median 0) `degenerate_zero` WINS MAE (0.12457, ≤ every real arm) while losing
   CRPS to every real arm. On hits/TB (median ≥ 1) it does not. Selecting on MAE would have
   crowned "predict zero for everyone" on the HR leg — the registered reason MAE was forbidden.

4. **DSR-CONV did real, visible work on TB.** With the two forward-declared degenerates left in
   `V`, the whole-field DSR is **0.0000** (their huge consistent losses inflate the dispersion
   term); the binding degenerate-excluded figure is **0.9993**. Both reported per the prereg;
   the declaration was made before the run, so this is the legitimate use (⛔ never
   retroactive). n_trials stays 7 throughout.

5. **The market's ~2–3pp over-lean is real but NOT fixable by a level shift (NF-D15 g′).** The
   matched level-only foil (market minus the training-period mean gap) fails to beat the raw
   market on hits (0.2390 vs 0.2388 pooled — the per-fold market bias flips sign across folds)
   and gains only ~0.0002 on TB. So the model's Brier win over the market is per-row content,
   not a level correction — and correspondingly the model's own bias does NOT sit nearer zero
   (hits: model −0.02 vs market +0.01). The "persistent negative level gap" from the prereg is
   a pooled average over folds whose bias moves; a constant de-bias is not the mechanism.

## Anchor honesty (what a reader should check first)

- `degenerate_zero` / `degenerate_marginal` LOSE CRPS on every leg (two-sided metric proof);
  `degenerate_marginal` is beaten by only ~2.3–2.7% (hits/TB) — the market-selected population
  compresses between-batter variance, so per-batter content is real but modest.
- Per-form peeking oracles (NF-D16 g‴) respected everywhere except two ε-violations
  (HR `hurdle_nb` by 1.7e-4, TB `glm_poisson` by 7e-5): both are the NF1.9 (f) capacity effect
  — the oracle fits the ~20k-row eval fold while the honest arm trains on ~95k rows — and the
  operative matched-n gate (`oracle_beats_matched_n`) passes on every leg. Not a metric
  inversion.
- lgbm's oracle gap (in-sample 0.353 vs OOS 0.445 on hits) shows the GBM has capacity the
  features can't cash OOS — consistent with the fixed-config GBM tying, not beating, the GLM.

## Binding constraints honored

- **HR per-fold-only benchmark** (§9.1): enforced by `guard_no_pooled_hr_benchmark`, which
  RAISES on any pooled HR emission (pinned by tests); every HR figure sits beside its fold's
  two-sided coverage share (95.4/92.5/90.2/93.2/94.2/**15.6%** — 2026H1 is Pinnacle-only).
- **6 folds is the ceiling**: no window widening attempted; nulls classified via
  `cv_power.classify_null` with DSR-CONV V-provenance flags.
- **Regular season only**: substrate boundary; any application to postseason is extrapolation.
- **Market-blind**: price columns are a FORBIDDEN set the design-matrix builder re-checks at
  fit time (raises), pinned by a RED-provable test.

## Caveats to carry forward

- The lgbm arm is a single fixed configuration (pre-registered, untuned) — its loss is a weak
  null for the GBM *class*; a tuned re-run is a legitimate future registration if TB's win
  motivates it. It does NOT weaken the TB ship (the winner is the simpler form).
- Integer-line rows (~1.5%) are excluded from the market-benchmark comparison (pushes grade
  as "under" in the stored `y_over`, which would bias against the market side).
- The market comparison grades the CLOSING consensus; nothing here says anything about
  beatable prices, timing, or vig — `best_alpha = 0`.
- 2026H2 rows exist in the substrate and were used nowhere (not a registered fold).

## What would follow (PM decisions, not session actions)

1. TB `glm_nb` is a ratified-but-held research champion: any serving surface (e.g. a TB
   projection page analogous to E5.5 K-projections) is a NEW story with its own runtime gate;
   nothing auto-deploys from this work.
2. HR: the two-sided benchmark keeps collapsing (Pinnacle-only from 2026-07). If a future HR
   surface is wanted, the grading estimand must be re-registered against the one-way
   "anytime HR" presentation instead.
3. A calibration surface ("our P(over) vs the de-vigged line, no bet") on hits/TB would be
   honest-framing-compatible (6/6-fold Brier advantage), but is a product decision.

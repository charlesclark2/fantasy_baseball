# NF-MARGIN1 pre-registration — per-player interval/tail calibration of the hurdle champion

**Committed AFTER the diagnosis stage and BEFORE the bake-off run.** Constants live in
`margin_calibration.py`; the runner (`run_nf_margin1_interval_calibration.py`) reads them
(NF-D16 discipline). This file is the narrative copy.

> ⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**: this story promotes
> nothing, publishes nothing, retrains nothing. A clearing arm's retrain/promote path is blocked
> on NF-C6 Ph2 + NF-G0 and is an operator decision.

## 1. Why this story — the frontier moved to the marginals

Three consecutive component studies are null against the injury-aware `lgbm_hurdle` champion:
NF-W3 (environment: ceiling 2–3% of champion CRPS, unforecastable), NF-W4 (availability: ceiling
8–28%, the forecastable slice already priced), NF-W5 (correlation: ceiling ≤0.5%, residual
same-team PIT correlation ≈ 0 outside QB structure). **The motivating measurement is NF-W5's
diagnostic that outlives its null** (`ablation_results/nf_w5_opportunity_allocation.md`, the
coverage line): the assembled champion's TEAM-TOTAL predictive under-covers — **coverage(80)
0.706 vs the 0.80 floor (n=2,174 team-weeks, binomial SE 0.0086 ⇒ ~11 SE)** — under EVERY
copula including the peeking oracles. Even perfect dependence knowledge does not fix it ⇒ the
defect is MARGINAL-SHAPE, in the per-player predictive.

## 2. The structural suspect, visible in the code

The champion's quantile learners fit 9 knots ending at 0.05/0.95 (`WP.FIT_LEVELS`);
`interp_to_levels` extends them FLAT onto the 39-level grid's 0.025/0.975 ends ("a conservative
tail" — it is the opposite: it deletes the tails), and the NF-W5 sampler clamps there again. The
served per-player predictive carries **no tail model beyond its own 5%/95% knots**.

## 3. The diagnosis (ran FIRST, per the story card; 2 folds 2025H1–H2, honest OOS, atom-aware
randomized PIT — `nf_margin1_diagnosis_smoke.{json,md}`)

| pos | P(u<0.025) | P(u>0.975) | Var(z) | cov50 | cov80 | cov95 | cov99 |
|-----|-----------:|-----------:|-------:|------:|------:|------:|------:|
| QB  | 0.065 | 0.052 | 1.32 | 0.682 | 0.811 | 0.901 | 0.901 |
| RB  | 0.039 | 0.049 | 1.11 | 0.641 | 0.842 | 0.930 | 0.930 |
| WR  | 0.038 | 0.040 | 1.13 | 0.647 | 0.857 | 0.946 | 0.946 |
| TE  | 0.025 | 0.044 | 1.05 | 0.700 | 0.877 | 0.954 | 0.954 |

Reading (this fixes the arm expectations below, in advance of any arm being scored):

- **The tails are too tight at every position** — beyond-grid PIT mass is 1.6–2.6× its nominal
  2.5%/side; the right tail everywhere, the left tail worst at QB. Var(z) > 1 everywhere.
- **The 50% central interval OVER-covers by 14–20pp** — the shoulders are too WIDE. This is a
  SHAPE (kurtosis) defect, not a variance defect: mass must move from the shoulders into the
  tails, not be added everywhere.
- **cov95 ≡ cov99 identically** — the structural signature of the flat tail (q995 ≡ q975).
- The team-total re-check reproduces NF-W5's defect on these folds (coverage(80) 0.662) with
  near-symmetric misses (17.1% below q10 / 16.7% above q90) ⇒ BOTH tails of the sum matter.

## 4. The field (per position; every construction is a monotone level map over the SAME champion
bank — the identity map reproduces the incumbent byte-for-byte, guard-tested)

**Foils** (never shippable; the best foil binds; the arm's verdict word is vs the best foil,
the calibration gate is vs the incumbent):

- `incumbent` — the champion as served (flat tails, the as-sampled object).
- `pit_recal_global` — the position-POOLED nonparametric recalibration (the NF1.8
  pooled-conformal foil: prices whether per-position conditioning earns anything).

**Real arms** (4 structurally different classes — §0.5 minimum):

1. `pit_recal_pos` — nonparametric monotone level map = empirical quantile function of the
   calibration PITs, per position. Distribution-free; can move shoulder mass and within-grid
   tail mass; CANNOT put mass beyond the grid (clamped — declared limitation).
2. `pit_recal_tail` — the same map + exponential tails beyond the grid ends (mean-excess fit).
   The ONLY class that can put mass beyond the champion's q025/q975. The paired contrast
   `pit_recal_tail` − `pit_recal_pos` is the pre-registered TAIL-CHANNEL attribution
   (NF-D10 (g)) and gets its own BH family.
3. `level_widen` — g(τ) = 0.5 + (τ−0.5)·w, **w ≥ 1 by grid construction** (the NF1.7 (d)
   widen-only clamp IS the grid; monotone widening guard-proved). Prices the naive
   "under-dispersed ⇒ widen" fix.
4. `zscore_affine` — g(τ) = Φ(μ̂ + σ̂·Φ⁻¹(τ)), (μ̂, σ̂) the calibration normal-score moments
   (the analytic Var(z)=1 anchor, MH2.1 (b)). Two-sided BY DECLARATION (may sharpen; it is not
   labelled widen-only). A variance fix.

**Anchors** (excluded from PBO and the DSR trial field): `zero_width` + `max_width`
(sharpness bracketed two-sidedly, NF1.7 (c); ⭐ `max_width` must SATISFY the 0.80 coverage floor
while LOSING both proper scores — the NF1.8 proof that the floor is a constraint, not a
criterion); `permuted_recal` (map fit on PITs of within-(position, week) permuted outcomes;
must not beat the incumbent, fails closed on an unevaluable p); one peeking `oracle__<form>` per
parametrized form fit on the TEST fold's own PITs (NF-D16 (g‴)), floored AT MATCHED n
(NF1.9 (f), `matched_n__<form>` refits on the most recent min(n_test, n_cal) calibration rows).

## 5. Fitting — honest OOS PITs

Maps are fit on a CALIBRATION SLICE: the most recent train global weeks totaling
≥ max(6000, 20%·train) rows, with the champion refit on the remaining core (PURGE_WEEKS gap).
⚠️ In-sample PITs of a boosted model are optimistically flat — a map fit on them
under-corrects; the split is structural, not tuned. Scored arms apply the cal-fit maps to the
full-train champion's test predictions.

## 6. Metrics — declared before any arm score

- **PRIMARY (selects + gates): `crps_q199`** — CRPS via the 2×mean-pinball identity over 199
  levels (0.005…0.995). WHY NOT `crps_q39`: the diagnosed defect lives partly BEYOND the
  champion's grid; a metric evaluated only there is structurally blind to any arm that models
  the tails (the instrument must SEE the fix — MH2.1, on levels instead of stratifiers). The
  incumbent is scored on the same grid with its as-served flat tails.
- **The story card's gate "improves per-player coverage toward 0.80 AND the interval score"** is
  operationalized per E2.1-r (a) — ⛔ a |coverage − 0.80| target is the recorded inversion — as
  two named gate clauses vs the incumbent: `interval_score_improves` (mean Winkler-80 falls) and
  `pit_flatness_improves` (pooled randomized-PIT max-decile-deviation falls). Coverage(80)
  remains a FLOOR (0.80, blocking beyond 3 binomial SE, pooled over rows per position).
- Co-reported, never select: coverage at 50/80/95/99, Var(z), beyond-grid PIT mass, and the
  **team-total re-check** (independence copula on the NF-W5 CRN base — the incumbent row is an
  exact reproduction anchor of the motivating coverage number; report-only).

## 7. The gate (per position; SHIP = all clauses; refusals classified)

`beats_foil` (crps_q199) ∧ fold clause (`cv_power.fold_consistency_clause`) ∧ PBO < 0.2 ∧
DSR ≥ 0.95 ∧ BH binding ∧ degenerates lose ∧ permutation behaves ∧ per-form oracle floors at
matched n ∧ coverage floor ∧ `interval_score_improves` ∧ `pit_flatness_improves`.

Two pre-registered BH families, own-family AND pooled computed, the stricter binds (MH2 (a)):
`{margin_arm_QB..TE}` and `{margin_tail_QB..TE}`. Null states via `cv_power.classify_null`
(n_arms=4, V measured excluding degenerates) with the NF-D18/MH2.7 hand check for
anchor/calibration-only refusals (CONSTRAINT_REFUSED, no sample-size trigger); ⚠️ the
`classify_null` n_arms=1 mis-render is a known instrument bug and does not arise here (n_arms=4),
and any "smaller field" remedy is auto-flagged SUSPECT below the declared 4-arm family (MH2.2).

## 8. Expectations fixed by the diagnosis (attributable in advance)

- `level_widen` is EXPECTED TO LOSE / clamp at w=1: the shoulders are already too wide, so a
  widen-only knob has nothing admissible to do. Its loss PRICES the naive fix.
- `zscore_affine` is EXPECTED to underperform the nonparametric maps: a single σ is a variance
  fix for a kurtosis defect (it must widen shoulders to widen tails).
- `pit_recal_tail` is the diagnosis-consistent class; the tail-channel contrast is expected
  positive. If `pit_recal_pos` ties `pit_recal_tail`, the beyond-grid channel is immaterial at
  the player grain and the defect is shoulder-only — either way the contrast attributes it.
- The team-total coverage should move toward 0.80 under the winner's marginals; a winner that
  improves per-player scores but NOT the team-total closes the NF-W5 loop negatively (recorded).

## 9. Constraints (NF-W0, inherited — this study adds NOTHING to the frame)

- Matrix = the NF-W2d two-era build through `build_matrix_w2d` verbatim: allowed-feature
  contract, roster-first frame, `assert_point_in_time` PIT gate fail-closed, snap features
  NULL-bearing (⛔ no fillna(0)), ⛔ no markets/weather/depth-rank/inactive sources.
- NF-MARGIN1 introduces NO new source, NO new features, NO new joins — its only inputs are the
  champion's own predictive quantiles and the realized `fantasy_points` label.
- Reducers refuse a non-finite predictive (`assert_finite_samples`); verdict words are three-way
  and derived at report time, failing closed to TIES (NF-W2e); `--rewrite-report` re-derives the
  whole verdict layer from the stored selections with zero refit.

## 10. Folds / deflation constants

The NF-W1 axis verbatim: 8 expanding-window half-season blocks 2022H1…2025H2, PURGE_WEEKS=2,
PBO<0.2, DSR≥0.95, FDR q=0.10, coverage floor 0.80 (3-SE blocking), seed 20260812. Capture-era
folds (2025H1, 2025H2) reported separately (report-only, NF-W2d/W2e).

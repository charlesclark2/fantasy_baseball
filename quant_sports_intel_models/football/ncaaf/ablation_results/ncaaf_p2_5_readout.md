# NCAAF-P2.5 — total / joint-distribution SHAPE repair · READ-OUT

**Verdict: `REFERENCE_STANDS` — the served P1.4/S1 shape stands. Null classified
`CONSTRAINT_REFUSED` (binding half: constraint), with the statistical shortfall reported.**

_Decided 2026-08-19 · 8 season-forward purged folds (2018–2025, 6,024 OOS games) · declared field 10
· `best_alpha = 0` · market-blind · deploy-held (NCAAF is not served)._

Pre-registration: `ncaaf_p2_5_preregistration.md` (locked before scoring; §8 records eight
specification amendments, all made before the decisive run).
Machine record: `ncaaf_p2_5_distribution_shape.{json,md}` · scores: `ncaaf_p2_5_shape_scores.json`.

---

## 1. The one-line answer

**The registered mechanism is REAL and measured — and no arm cleared the pre-registered ship bar.**
The total's residual is genuinely **right-skewed** (fitted skew-normal α ≈ **+2.12** on the total vs
+1.02 on the margin), and modelling that skew cuts the total's PIT deviation by **62%**
(0.0170 → 0.0065) and the joint PIT by **25%** (0.0130 → 0.0097) while *improving* CRPS. But the
skew arms pay for it **in the tails** and fail clause C5, and the best-CRPS arm (`key_number`,
+0.0287) fails the DSR gate at 0.311 and is not floor-verified. So the served shape stands.

## 2. ⚠️ The premise, re-measured — the card's number is from a superseded contract

The story card motivates the work with total `PITdev 0.0218`. That figure is
`ncaaf_p1_4_calibration.json` (contract `strength_only`, 2026-07-23) — **superseded**. What actually
SERVES is NCAAF-P2.1-S1-serve's `strength_pace` contract:

| | P1.4 `strength_only` (the card) | **S1-serve `strength_pace` (what serves)** |
|---|---|---|
| total `pit_max_decile_dev` | 0.0218 | **0.0173** |
| total `pit_mean_dev` | **0.0263** | **0.0149** |
| total `pit_is_flat` | ❌ | **✅** |

Two consequences, both acted on before scoring:

1. **The foil is the SERVED config.** Measuring against 0.0218 would hand every candidate a 0.0045
   head start it did not earn. Gate R proves the foil is the served model: the pooled OOS refit
   reproduces the served σ to **δ = 0.0000 on both axes** over the same 6,024 games.
2. **P1.4's total failure was `pit_mean_dev` 0.0263 — a LOCATION defect, not a tail defect**, and the
   S1 pace term already repaired most of it. So the residual target was genuinely smaller than the
   card assumes, and a null was the honest prior going in.

## 3. DATA PREREQ — weather: **ABSENT**, dropped, not fabricated

The card conditions weather-driven variance terms on confirming availability first. Measured: the
assembled P1.3 matrix carries **207 columns and zero** matching `weather|temp|wind|precip|humid`, and
neither `ncaaf_data_inventory.md` nor `ncaaf_mart_inventory.md` documents a weather feed. ⇒ weather
is **removed** from the registered driver set; `game_venue_is_dome` and `game_venue_elevation_m` are
registered as the partial environment proxies they are, labelled as such. A guard forbids a later
session re-adding a fabricated weather column.

📌 **This also answers P2.1's H10 (WEATHER)**, which carries the same "confirm venue weather is
available first" condition. It is not available.

## 4. The design — a coherent field over a FROZEN mean

Every arm consumes the same per-game (μ_margin, μ_total) from the served `ridge / strength_pace`
config, refit walk-forward per fold, and differs ONLY in the conditional shape around it. That makes
ΔCRPS attributable to shape alone, keeps the mean out of scope (it is P2.1/P2.6's), and — the reason
that matters for the gate — keeps the field **coherent**, which is what `SR0` is taxed by
(MH2.5 / NF-W6b-C). The invariant is enforced on the SCORED sample arrays (clause C7), not asserted.

Two return series, **declared separately** (the NCAAF-P2.1-S1 lesson): PBO runs CSCV over 32 per-
bucket observations; the binding DSR runs on the 8 per-FOLD matched-pair deltas. Anchors are
diagnostic and excluded from BOTH `n_trials` (= 10, the declared field) and `V` (= 0.904, measured
over the real arms only) — MH2.1 (a).

## 5. Leaderboard — primary = pooled total-CRPS (lower better)

| arm | doc §4.1 item | CRPS | gain | folds won | total PITdev | mean-dev | calib_80 | joint PIT | DSR | p | refused by |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **`incumbent` (FOIL)** | the served form | **9.40526** | — | — | 0.0170 | 0.0147 | 0.807 | 0.0130 | — | — | — |
| `key_number` | discrete-score simulation | **9.37661** | **+0.0287** | **7/8** | 0.0124 | 0.0107 | 0.804 | 0.0129 | 0.311 | **0.0049** | **C8** + DSR |
| `skew_normal` | skew-normal | 9.39268 | +0.0126 | 6/8 | **0.0065** | **0.0068** | 0.801 | **0.0097** | 0.002 | 0.0547 | **C5** |
| `skew_t` | skew-t | 9.39313 | +0.0121 | 6/8 | 0.0071 | 0.0070 | 0.798 | 0.0097 | 0.004 | 0.0532 | **C5** |
| `copula` | copula w/ non-parametric marginals | 9.39622 | +0.0090 | 6/8 | 0.0092 | 0.0072 | 0.806 | 0.0095 | 0.001 | 0.0837 | **C5** |
| `student_t` | bivariate Student-t | 9.40623 | −0.0010 *(TIE)* | 4/8 | 0.0189 | 0.0150 | 0.799 | 0.0142 | 0.000 | 0.665 | C2, C6 |
| `mixture` | Gaussian / regime mixture | 9.40697 | −0.0017 | 2/8 | 0.0116 | 0.0113 | 0.808 | 0.0127 | 0.000 | 0.791 | C5 |
| `quantile_boost` | quantile / distributional boosting | 9.43566 | −0.0304 | 2/8 | 0.0139 | 0.0076 | 0.783 | 0.0122 | 0.000 | 0.981 | C5 |
| `cond_het` | conditional heteroskedasticity | 9.44038 | −0.0351 | 0/8 | 0.0148 | 0.0140 | 0.802 | 0.0157 | 0.000 | 0.995 | C5, C6 |
| `home_away` | separate home/away score dists | 9.46567 | −0.0604 | 1/8 | 0.0382 | 0.0074 | **0.868** | 0.0344 | 0.000 | 0.998 | C1, C2, C3, C5, C6 |

Deflation: **PBO 0.000** (32 buckets, 1,000 CSCV combos) · contender spread **0.947%** of the foil ·
per-fold flip mass **6/8 on `key_number`** · BH-FDR cutoff 0.005556 (only `key_number`'s p clears).

⭐ **PBO 0.000 with 6/8 flip mass is not a tied field** — the in-sample best persists out-of-sample,
i.e. the search is stable and `key_number` really is the best arm on this metric. It is refused by
the deflation BAR, not by instability. That distinction is the NF1.8 requirement and it points the
successor at variance, not at search discipline.

## 6. What the study established (the findings outlive the null)

**(a) The total's shape defect is SKEW, not tail weight — measured.**
`skew_normal` fits α = **+2.12** on the total. `skew_t`'s total ν pins at its **60.0 upper bound**
(the Normal limit) — with the skew modelled, no fat tail is wanted. And `student_t` *alone* (total
ν ≈ 39, no skew) is a **TIE** (−0.0010, inside the 1e-3 band) that fails C2. ⇒ heavy tails do
nothing here; the asymmetry is the whole effect. Mechanistically that is what a football total looks
like: a shootout has no mirror image below zero points, so the residual has a right tail and the
median sits below the mean — which is exactly the `pit_mean_dev` the incumbent carries.

⭐ **Cross-vertical corroboration:** MLB MH2.6/MH2.8 found the SAME defect in the served `total_runs`
predictive ("a symmetric Normal against a right-skewed target") and reached the SAME shape of
verdict (`INCUMBENT_STANDS`, refused on a deflation gate). Two independent sports, one mechanism,
one refusal shape — that is a program-level finding, not a coincidence, and it raises the prior that
a *symmetric* predictive is the wrong default for any scoring total.

**(b) The skew repair is bought in the TAILS — which is why C5 exists.**
The three skew/non-parametric arms improve the body and the joint while each costing tail-CRPS:

| arm | tail-CRPS | vs foil |
|---|---|---|
| `incumbent` | 5.49348 | — |
| `skew_t` | 5.49750 | +0.0040 |
| `skew_normal` | 5.49912 | +0.0056 |
| `copula` | 5.50121 | +0.0077 |
| `key_number` | **5.48063** | **−0.0129** |

A plain CRPS read would have shown three clean winners. The threshold-weighted statistic is what
shows the trade, and it is the reason none of them ships. (`key_number` is the only arm that improves
the body *and* the tails — and it is refused elsewhere.)

**(c) The conditional-variance sub-model is a clean NEGATIVE — attributable, not merely absent.**
`cond_het` (the story's headline candidate) LOSES by 0.0351 and wins **0 of 8 folds**, and its
matched permutation anchor — the identical machinery with the driver rows SHUFFLED against the
residuals — **BEATS it by 0.0058**. ⇒ the registered drivers (pace · mismatch · favourite size ·
explosiveness · QB uncertainty · early season · the two environment proxies) carry **no variance
information beyond the marginal**, and fitting them costs a real overfitting penalty at n≈736. The
permutation is what makes that attributable rather than a bare rank (NF-D10): shuffling *improves*
the fit, so the signal is not merely small, it is absent. Note `cond_het` NESTS the incumbent (its
driver set includes `log_strength_var`), so this is not a specification accident.

**(d) The per-side count form OVER-disperses.** `home_away` (correlated NegBin team points, which
relaxes the independence P1.4's `count` form forced) covers **0.868** against a nominal 0.80 and is
the only arm failing PIT flatness outright. Relaxing ρ_sides did not rescue the per-side count form.

**(e) A distributional booster is KNOT-LIMITED at this n.** An α-quantile cannot be estimated inside
a leaf smaller than `1/α` rows; at ~736 inner-holdout rows the arm is confined to a 0.05–0.95 knot
band and still under-covers (0.783). That is honest information about the candidate, and it is
recorded rather than hidden inside a loss (amendment A8.4).

## 7. Why it did not ship, stated in the unit that binds

`key_number` cleared every calibration clause, PBO, and BH-FDR (p = 0.0049 ≤ 0.005556) and was
refused by two things:

* **DSR 0.311 vs the 0.95 gate.** Its per-fold Sharpe **1.243** sits **BELOW** the field's deflated
  benchmark **SR0 1.497**. `n` enters DSR only through `√(n−1)`, so it scales a positive gap and
  **cannot create one** ⇒ `DSR_UNREACHABLE`. ⛔ **No number of additional seasons clears this**, and
  reporting a "re-test in N seasons" trigger would be actively misleading (NF-D18 / MH2). The
  instrument was also asked whether a smaller field is the lever and answered no — *"even a 2-arm
  field does not clear at this fold count and dispersion"* — so ⛔ a narrower re-registration is not
  the remedy either. **The only lever is a lower-variance design** (more rows per fold, or a sharper
  metric).
* **C8 — it is not floor-verified.** Its own-form peeking ceiling came in 0.0042 below it. The cause
  is recorded rather than explained away: the peek is a peeking **MLE** while the metric is **CRPS**,
  and for an arm whose scale reaches the predictive through a non-Gaussian lattice transform those
  optima need not coincide. The clause is left FAILING (E2.1-r).

Because a hard clause binds and no fold count moves it, the null is recorded **`CONSTRAINT_REFUSED`**
(binding half: constraint) rather than `POWER_LIMITED`, per NF-D18 — while the instrument's own
`DSR_UNREACHABLE` verdict is reported verbatim beside it rather than hidden (NF-W7f).

## 8. Anchors — all behaved, and one earned its keep

| anchor | required | observed |
|---|---|---|
| per-form peeking ceiling | nothing beats its OWN form | 13/14 clear with a +0.005…+0.219 gap; `key_number` beaten by 0.0042 ⇒ **C8**, per-arm |
| `zero_width` (σ at floor) | LOSE the metric AND FAIL the floor | CRPS 11.830 (+2.43) · calib_80 **0.182** ✅ |
| `max_width` (σ × 3) | SATISFY the floor and LOSE the metric | calib_80 **0.999** · CRPS 14.018 (+4.61) ✅ — the NF1.8 proof that the floor is a constraint a degenerate satisfies, never a criterion it wins |
| `coverage_target` (calib_80 → exactly 0.80) | SATISFY the constraint, not WIN the selection | calib_80 **0.801** · CRPS 9.40400 (beats the foil by 0.0013) · total PITdev **0.0178 — WORSE than the foil** ⇒ fails C2, does not ship ✅ |
| `permute` (shuffled drivers) | mechanism read, never a validity gate | BEATS `cond_het` by 0.0058 ⇒ the conditional-variance channel is **not real** |

⭐ **The `coverage_target` result is the E2.1-r proof landing exactly as intended, and it landed the
interesting way.** A pure σ-rescale tuned to hit 80% coverage *does* edge the foil on CRPS — so a
CRPS-only reading would have promoted a degenerate that makes **no shape change at all**. It is
stopped by C2, because rescaling σ cannot repair a PIT it leaves alone (its PITdev gets *worse*).
That is precisely why coverage is a FLOOR and the ship rule is more than its primary metric.

## 9. Honest framing

`best_alpha = 0`. This story could only have improved the **shape/honesty** of a probability, never
claimed an edge; the game model stays MARKET-BLIND (no market input reaches any driver, fit or
sampler — `assert_market_blind` runs on every contract and on the driver list). NCAAF is not served,
so nothing here is a deploy. **No re-point is owed: the served artifacts are unchanged.**

## 10. What a successor would need (⛔ not carded here, and not "more seasons")

The mechanism is real and the refusal is a variance/anchor problem, so a successor is legitimate —
but it must be a **FRESH registration**, never a re-cut of this field (MH2.2):

1. **A lower-variance design.** DSR is unreachable at this per-fold noise; the lever is more rows per
   fold or a sharper matched statistic, not more calendar.
2. **A skew arm that does not pay in the tails.** The measured trade is body-vs-tail; a form that
   fixes the asymmetry while preserving tail mass (rather than redistributing into it) is the
   obvious target, and C5 is the statistic that would judge it.
3. **A CRPS-optimal per-form ceiling** for arms whose scale passes through a non-Gaussian transform,
   so C8 can bind on evidence rather than on estimator mismatch.
4. ⛔ **NOT** the conditional-variance channel on this driver set — (c) above closes it attributably,
   and ⛔ **NOT** a weather-driven variance term until a weather feed exists (§3).

# NCAAF-P2.1-S1b — is the composite's margin over the 8-column block EARNED?

_Decided 2026-08-17 · matched pair vs `pace` · 7 trials · 8 purged folds · 8,325 games · declared real-arm field 2 · primary `pace_axis`_

**Pre-registration:** [`ncaaf_p2_1_s1b_preregistration.md`](./ncaaf_p2_1_s1b_preregistration.md) — written and committed BEFORE the first S1b score.

## What this run can and cannot establish (read before the verdict)

* ⚠️ **No held-out season exists.** S1's folds are eval-years 2018…2025 — every completed FBS season in the cache; 2026 is unplayed (opener 2026-08-29). S1b shares S1's measurement substrate **in full** and cannot replicate the effect on data S1 did not see.
* ⚠️ **The harness is deterministic, so S1b's CRPS is byte-identical to S1's** (gate R verifies exactly this). Re-running the battery is a REPRODUCTION, not a new measurement.
* ✅ **What IS new:** S1 measured every arm against the 25-column `reference` and recorded the block-vs-composite delta as an attribution read its own harness labels *"declared; reported, **never gated**"*. S1b registers that delta as the PRIMARY contrast and gates it — fold-consistency, BH-FDR, PBO, DSR and an anchor set have never been applied to this statistic before.

## Verdict

**MARGIN_NOT_EARNED**

> NO CHANGE. The served representation continues to stand on S1-serve §2's MECHANISTIC argument, which is independent of this margin. The record states the margin is NOT independently claimable — the status quo of §6, now measured rather than asserted.

| gate | value | bar | |
|---|---|---|---|
| anchors valid (incl. the no-pace degenerate) | True | all seven checks | ✅ |
| **R** — reproduction of S1's per-fold CRPS (foil + both arms + degenerate) | max abs dev 0.0 | < 0.0001 | ✅ |
| primary arm-level gates (eligible · not a tie · Δ>0 · BH-FDR · fold clause) | False | all | ❌ |
| PBO (CSCV, candidate set = eligible real arms + the foil) | 0.331 | < 0.2 | ❌ |
| **DSR (per-FOLD matched pair, declared field, degenerate-excluded — BINDING)** | **0.9687** | ≥ 0.95 | ✅ |
| BH-FDR cutoff | 0.0 | α = 0.05 | — |
| fold-consistency (calibrated) | 6 of 8 wins | false-fire ≤ 0.20 | — |

**Where the contrast can act (S1b-V5 / NF-D20).** The block and the composite differ ONLY in the six per-side level columns; on NULL-pace rows both impute to the train mean, so those rows contribute **exactly 0** to the delta. Active on **91.4%** of eval rows (5,507/6,024) — the pooled delta is diluted by the remainder. Reported, never used to rescale the metric.

## Anchors — the two-sided proof the metric is not inverted

| anchor | reading | expectation | holds |
|---|---|---|---|
| `oracle_peek` (ORACLE FLOOR) | CRPS 1.4042 vs best real 18.4387 | nothing may beat it | ✅ |
| `permute` | CRPS 21.7975, calib80 0.677/0.782, coverage floor FAILED | must LOSE | ✅ |
| `zero_width` | CRPS 23.1887, calib80 0.195/0.185, coverage floor FAILED | must LOSE + FAIL the floor | ✅ |
| `max_width` | CRPS 27.4594, calib80 1.000/0.999, coverage floor satisfied | must SATISFY the floor + LOSE | ✅ |
| `reference` ⭐ (NO-PACE degenerate, S1b-specific) | CRPS 18.5190 vs foil 18.4570 | the NO-PACE contract must LOSE to the block — orients the matched pair | ✅ |

## The field — the matched pair, both series side by side

`Δ vs foil` > 0 ⇔ the arm beats the **8-column block**. `SR/fold` is the DECLARED DSR series (8 obs); `SR/bucket` is the 32-obs series, reported so the series choice is auditable.

| arm | Δ vs foil | fold wins | p (1-sided) | BH | eligible | margin-PIT flat | tie | SR per FOLD | SR per BUCKET | state |
|---|---|---|---|---|---|---|---|---|---|---|
| `pace_axis` ⭐ | +0.0184 | 6/8 | 0.0407 | — | ✅ | 4/8 (need ≥4) | — | 0.719 | 0.436 | POWER_LIMITED |
| `pace_total_axis` | +0.0170 | 5/8 | 0.0578 | — | ✅ | 5/8 (need ≥4) | — | 0.635 | 0.404 | POWER_LIMITED |
| `pace` (FOIL, 8-col block) | — | — | — | — | — | 5/8 | — | — | — | matched incumbent |

`pace_axis` per-fold Δ vs the block by eval season: 2018 +0.0013, 2019 +0.0445, 2020 -0.0042, 2021 -0.0120, 2022 +0.0566, 2023 +0.0222, 2024 +0.0267, 2025 +0.0047.

⚠️ **Calibration-constraint status of the primary.** `pace_axis` is margin-PIT flat in **4/8** folds against a threshold of ≥4 — it passes **exactly at the boundary**, and is 1 fold(s) worse than the block (5/8). ⛔ The constraint is inherited verbatim and is NOT tightened (NF1.8: a floor is never a target, and tightening it after seeing a result is the E2.1-r inversion). Recorded as a caveat on the representation, not remedied by moving the bar.

## Beside PBO — is this a TIE or an UNSTABLE pick? (NF1.8, post-verdict disclosure)

A rank statistic alone cannot tell *"my pick is unstable"* from *"the candidates are tied"*, and the two readings imply opposite things for a representation that **already serves**. ⛔ The PBO gate binds on its own value; nothing here re-decides it.

* **Contender spread** — +0.01835 CRPS across {`pace_axis` 18.4387, `pace_total_axis` 18.4401, `pace` 18.4570}, i.e. **0.099% of the foil's CRPS**. The three representations are separated by a tenth of a percent.
* **Per-fold flip distribution** — which candidate is best on each of the 8 folds: `pace_axis` 4, `pace_total_axis` 2, `pace` 2. (Read off the same fold CRPS the gate uses — deliberately not a second CSCV implementation.)
* **Median OOS rank of the in-sample best** — **3.0 of 3** over 1000 CSCV combinations. ⚠️ In this instrument the rank runs 1…N with **HIGHER = better out-of-sample** (`ω = rank/(N+1)`), so the in-sample winner typically lands *first* out-of-sample — the opposite of an unstable selection.

⚠️ **PBO is a COARSE statistic on a 3-config field.** With N = 3, ω can only take the values 0.25 / 0.50 / 0.75, and a *middle* finish (ω = 0.50) already counts as an overfit event. Among three representations separated by a tenth of a percent, finishing second is close to a coin flip, so a PBO above the 0.2 gate is near-structural here rather than diagnostic of a fragile pick.

> E2.1-r: a HIGH PBO over a field whose candidates genuinely TIE is the NULL — 'which tied candidate wins is noise' — not evidence of overfitting; a high PBO with a WIDE spread IS overfitting. The SPREAD is the discriminator, so it is reported here beside the flip distribution rather than left for the reader to assume.

## DSR — the declared series binds; the others are disclosure

| figure | DSR | SR | SR0 | N trials | n obs | status |
|---|---|---|---|---|---|---|
| `per_fold_declared_field_degenerate_excluded` | 0.9687 | 0.7189 | 0.0826 | 7 | 8 | ⭐ **BINDING** |
| `per_fold_whole_field` | 0.0 | 0.7189 | 30.3672 | 7 | 8 | reported |
| `per_fold_lineage_inclusive` | 0.958 | 0.7189 | 0.1285 | 37 | 8 | reported |
| `per_bucket_REPORTED_ONLY` | 0.9892 | 0.4356 | 0.0311 | 7 | 32 | reported only |

**Moment sensitivity of the binding DSR (post-verdict disclosure, decides nothing).** `deflated_sharpe` estimates the series' higher moments from its 8 observations; here they are **skew 0.508, kurtosis 1.9888** — platykurtic, i.e. FAVOURABLE (thinner tails ⇒ a smaller denominator ⇒ a higher DSR). The binding DSR is **0.9687** at SR 0.7189.

⚠️ `deflated_sharpe` has **no** skew/kurt parameters — it always estimates them from the series — so a "Gaussian-moment DSR" cannot be obtained from it and is NOT fabricated here. The sensitivity is expressed on the instrument that *does* accept the moments: the DSR gate needs **7 folds** under the measured moments but **10** under Gaussian ones — against 8 available. At n = 8 the moment estimates are themselves noisy, so the DSR pass should be read as resting partly on them.

⚠️ This is also where the **same gate name is computed two ways** (MH2): `cv_power`'s reachability arithmetic defaults to Gaussian moments, and on this series that disagrees with the binding figure by three folds. This harness therefore passes the measured moments to `classify_null` explicitly — without that, the record would publish a *"+1 more season"* re-test trigger for a gate that has already PASSED.


`V` (cross-trial per-fold Sharpe dispersion): degenerate-excluded 0.0035 · whole field 479.5096 · per-bucket degenerate-excluded 0.0005.

⚠️ **On the 2-arm field, stated because a small field lowers `SR0` and that deserves a direct answer.** The pace representation set has exactly three mechanistically distinct parameterisations (all 8 columns / the two composites / the total axis alone). S1b makes one the foil, leaving two. **No arm was removed because it lost** — `pace_total_axis` is retained even though it is expected to tie. The lineage-inclusive figure above (N = 37) shows whether the verdict depends on the narrow count.

## Null classification

Classified with `cv_power.classify_null(n_arms=2, declared_field_size=2, degenerates_excluded_from_v=True)` on the DECLARED per-fold matched-pair series; the MACHINE flag `field_remedy_admissible` is read, never the prose (MH2.7).

| arm | primary | arm-gates | state | field remedy admissible | re-test trigger | reachable now |
|---|---|---|---|---|---|---|
| `pace_axis` | ⭐ | — | POWER_LIMITED | None | UNDEFINED — the instrument returned a non-positive fold requirement (folds_needed=0, extra_seasons=-8) because BH rejected every arm, leaving a degenerate cutoff of 0. The binding shortfall is NOT a fold count: it is the BH-FDR step itself — see `bh_shortfall` below. | **no — calendar-bound** |
| `pace_total_axis` | — | — | POWER_LIMITED | None | UNDEFINED — the instrument returned a non-positive fold requirement (folds_needed=0, extra_seasons=-8) because BH rejected every arm, leaving a degenerate cutoff of 0. The binding shortfall is NOT a fold count: it is the BH-FDR step itself — see `bh_shortfall` below. | **no — calendar-bound** |

⚠️ **The instrument's raw trigger for `pace_axis` was mis-rendered and is corrected above.** It returned `+-8 folds (⇒ 0 total) for certifiability` — a NON-POSITIVE fold requirement, which is not a re-test instruction but a mis-render of a state: BH rejected every arm, so the cutoff was the degenerate 0 and the certifiability arithmetic ran on it. The raw string is recorded verbatim in the JSON (`retest_trigger_raw_from_instrument`), never silently dropped. This is the MH2.7 `n_arms=1`-renders-as-a-fold-shortage family recurring on a second code path — ⭐ a defect hand-corrected downstream N times is a defect in the INSTRUMENT, and fixing `cv_power` is carded rather than done here (a shared instrument is pinned by cross-vertical guards — MH2.7).

**The binding shortfall for `pace_axis`, in the unit that actually binds.** ranked 1 of 2 by p-value, so the BH step is α·1/2 = 0.025; the observed p is 0.040747. The gap is what would have to close — a smaller p, i.e. a larger or less noisy effect, NOT a larger field (a bigger m RAISES the bar for rank 1). Observed p **0.040747** vs the required **0.025** — a gap of **+0.0157**.

⚠️ **The instrument's raw trigger for `pace_total_axis` was mis-rendered and is corrected above.** It returned `+-8 folds (⇒ 0 total) for certifiability` — a NON-POSITIVE fold requirement, which is not a re-test instruction but a mis-render of a state: BH rejected every arm, so the cutoff was the degenerate 0 and the certifiability arithmetic ran on it. The raw string is recorded verbatim in the JSON (`retest_trigger_raw_from_instrument`), never silently dropped. This is the MH2.7 `n_arms=1`-renders-as-a-fold-shortage family recurring on a second code path — ⭐ a defect hand-corrected downstream N times is a defect in the INSTRUMENT, and fixing `cv_power` is carded rather than done here (a shared instrument is pinned by cross-vertical guards — MH2.7).

**The binding shortfall for `pace_total_axis`, in the unit that actually binds.** ranked 2 of 2 by p-value, so the BH step is α·2/2 = 0.05; the observed p is 0.057841. The gap is what would have to close — a smaller p, i.e. a larger or less noisy effect, NOT a larger field (a bigger m RAISES the bar for rank 1). Observed p **0.057841** vs the required **0.05** — a gap of **+0.0078**.

⛔ **A re-test trigger stated in folds/seasons is a FUTURE note, not a live re-test.** The fold count is calendar-bound (2018…2025 is every completed FBS season); a new fold requires the 2026 season to be played. And a `DSR_UNREACHABLE` state carries **no** re-test trigger at all — `n` enters only through `√(n−1)`, so it scales a positive gap and cannot create one (MH2 / NF-D18).

## Honest framing

`best_alpha = 0`. S1b changes no bet, no edge claim and no framing — it concerns which of two already-certified column sets carries a calibration term in a market-blind mean model. The edge bar (model-side ATS/OU > 0.5238 AND > placebo) is unchanged and unclaimed.

- foil `pace` vs-close: `{"ats_hit_rate": 0.5067, "ats_n": 4117, "ats_placebo": 0.4894, "ou_hit_rate": 0.5151, "ou_n": 4135, "n_with_close": 4187, "breakeven": 0.5238, "clears_edge_bar": false}`
- `pace_axis` vs-close: `{"ats_hit_rate": 0.504, "ats_n": 4117, "ats_placebo": 0.4894, "ou_hit_rate": 0.5151, "ou_n": 4135, "n_with_close": 4187, "breakeven": 0.5238, "clears_edge_bar": false}`

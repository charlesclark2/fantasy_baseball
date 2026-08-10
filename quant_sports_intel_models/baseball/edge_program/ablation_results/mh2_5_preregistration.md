# MH2.5 — PRE-REGISTRATION

> ⚠️ **Not an edge claim.** `best_alpha = 0`, `bet_paused = true`. A pricing/calibration study.

**Registered 2026-08-08, in source (`betting_ml/scripts/mh2_5_sigma_recalibration.py`, the `LOCK 1`
… `LOCK 9` block) BEFORE any arm was scored.** This file transcribes those locks so the record is
readable without opening the harness; the SOURCE is authoritative, and a guard test
(`betting_ml/tests/test_mh2_5_sigma_recalibration.py`) pins the constants that matter.

Results: `mh2_5_sigma_recalibration.md` (primary) and `mh2_5_sigma_recalibration_no2020.md` (the
declared COVID control).

---

## The question, and what it inherited

The served `total_runs` / `post_lineup` champion is the **v6 NGBoost Normal**, which predicts a
per-game σ. `mh2_1_rollback.md` measured two things about that σ on the 2026 served rows:

1. it generalizes weakly — RMS |Var(z) − 1| ≈ 0.12 in-sample vs ≈ 0.23 out of sample;
2. realized SD rises **+35%** across its own σ deciles while σ rises only **+23%**, i.e. the
   heteroscedasticity is real and **UNDER-expressed**.

MH2.5 was scoped from (2): *make per-game σ generalize and WIDEN its dynamic range — not flatten
it.* ⛔ The flat-σ arm is a **NULL TO BEAT**, never a proven improvement: MH2.1 promoted one and was
rolled back the same day.

⚠️ **(2) is a HYPOTHESIS this study TESTS, not an assumption it builds on.** It comes from one
season, n = 1,362, partly in-sample. The design below can refute it, and §0 of the result report is
the test.

## LOCK 1 — the window

- **PRIMARY:** `min_year = 2016`, 2020 KEPT → 11 seasons, **8 purged/embargoed folds**.
- **SENSITIVITY (mandatory):** 2020 dropped from BOTH train and eval → 7 folds. Run and reported as
  a declared control, never as an alternative headline. Identical to MH2.1's Lock 1 so the two
  studies are directly comparable. If the verdict flips between them, that fact is the finding.

## LOCK 2 — the field: 9 arms, DECLARED not discovered

Every arm shares the **incumbent's MEAN** and differs ONLY in σ. That is the NF-D15 (g′) matched-foil
discipline applied to the entire field: any difference between two arms is attributable to the
variance model and to nothing else. No arm may be dropped after a score is seen (MH2 §a).

| arm | role |
|---|---|
| `power_widen` | σ′ = a·σ̄·(σ/σ̄)^γ, (a, γ) fit in-fold by Gaussian NLL. **NESTS the incumbent (γ=1) and the flat null (γ=0)**; γ free over [0, 3] so it may widen or narrow. |
| `iso_widen` | isotonic regression of resid² on σ — a nonparametric monotone recalibration; contains `power_widen`'s map as a special case. |
| `var_glm` | a LEARNED variance head: ridge on log(resid²) over the 13 contract features, **ignoring the incumbent's σ entirely** — §0.5's required direct-learned foil. |
| `var_glm_plus_sigma` | the same head plus `log σ_incumbent` as a feature (the combination). |
| `incumbent` | the served v6 σ, verbatim. **THE BAR.** |
| `level_only` | ⭐ **THE MATCHED FOIL** — the incumbent's σ × ONE constant fit on the calibration split. Every candidate is level-corrected the same way, so without this arm a candidate could win purely by fixing the LEVEL while the story claims it fixed the SHAPE. |
| `flat_sigma` | ⚠️ **THE NULL TO BEAT** — one constant σ (MH2.1's rolled-back winner shape). |
| `over_disperse` | `level_only` × 1.5 — the `max_width` degenerate (NF1.8 (3)). |
| `under_disperse` | `level_only` ÷ 1.5 — its mirror. A *criterion* a degenerate wins is fatal, so the metric is proven **two-sided**. |

`n_trials = 9` for PBO and DSR.

## LOCK 3 — diagnostic anchors are NEVER trials

Excluded from `n_trials`, from DSR's `V`, and from PBO (MH2.1 (a) — the `oracle_floor` DSR-field
leak, where the anchor that exists to police the gate silently SET its bar).

- `oracle_bin` — ⭐ **the inversion GATE.** Each bin gets its own REALIZED SD as σ, on the very
  partition the headline is scored over, so it is conditionally calibrated **by construction**. Its
  score IS the metric's empirical noise floor. Nothing may beat a construction; anything that does
  HALTs the run.
- `oracle_<form>` (one per candidate) — peeking same-form arms. ⚠️ **A HEADROOM DIAGNOSTIC, NOT A
  GATE.** A peeking oracle is a floor only at matched FAMILY *and* matched SAMPLE (NF1.7 (b)), and
  matched sample is often unobtainable here — an oracle can only be fitted on eval rows, of which
  there are fewer than the calibration split in most folds. NF-D14: *a winner can legitimately beat
  a peeking oracle at unmatched n.*
- `perm_sigma` — the incumbent's σ permuted across games. **Registered in advance to degrade to
  roughly `flat_sigma`** (NF-D16 sibling (1): state an anchor's expected behaviour before the run, so
  a near-tie is not presented as a passed test).

## LOCK 4 — the metric and its PARTITION (the method lock)

- **Primary metric:** RMS |Var(z) − 1| across deciles of a validated common stratifier, pooled
  out-of-fold. `Var(z) = 1` per stratum is **analytic truth** — no oracle, no fitting, and (MH2.1
  (b)) **never anchored on the incumbent**, because an incumbent-relative metric inverts whenever
  the incumbent is the defective one and can only ever say *different*, never *better*.
- **Secondary:** the Winkler interval score (proper). Central-80% coverage is a **FLOOR**, ⛔ never a
  target (E2.1-r / NF1.8 — a coverage target is monotone in widening and `max_width` wins it).
- **Sanity only:** CRPS and PIT-KS. Both are structurally BLIND here — CRPS is mean-dominated and
  every arm shares the identical mean; PIT-KS is marginal, so a model that over-covers the calm
  games exactly as much as it under-covers the volatile ones passes it while being badly
  miscalibrated conditionally. That methodological point is what survives from MH2.1.

**Common stratifiers, fixed before the candidates exist and controlled by no candidate:**
`incumbent_sigma` (PRIMARY — the partition MH2.1's rollback validated) and `incumbent_mean` (an
independent robustness partition; mechanistically grounded, since for count-like totals the variance
grows with the level, and it is not a σ model at all).

⚠️ Each arm is also profiled on **its own σ** — a DIAGNOSTIC only. An own-σ partition can never be
the criterion: a flat-σ arm has no own-σ partition at all, so it would score ~0 by construction — a
criterion the degenerate wins outright (NF1.8).

**Validation bar (LOCK 4c), stated before it was measured:** a partition is admissible only if
realized dispersion demonstrably RISES across its bins — **Spearman ρ ≥ 0.30 AND endpoints ≥ 2.0
pooled SE apart** — with the full table (n, mean stratifier, realized SD, per-bin SE) published
whether it passes or fails. The bar sits well below the ρ ≈ 0.66 the rollback measured, so it tests
admissibility rather than re-asserting the known answer. **A partition that fails is DISQUALIFIED
and no Var(z) is read off it.** A σ-CV floor, a matched foil and a permutation null do NOT
substitute — MH2.1 had all three and still landed on strata whose ordering did not survive.

## LOCK 5 — the practically-meaningful effect

**`MH25_MEANINGFUL_RMS_GAIN = 0.05`**, derived from a SERVING quantity and fixed in advance (the
NF1.8 discipline). A Var(z) of `v` turns a nominal central-80% interval into realized coverage
2Φ(1.2816/√v) − 1; one percentage point of coverage error corresponds to |v − 1| ≈ 0.045. So an RMS
improvement below 0.05 is worth less than one coverage point across the volatility range and is not
a pricing-relevant improvement, however significant.

## LOCK 6 — the SHIP rule (default = INCUMBENT_STANDS)

A candidate ships only if **all** hold:

1. the pre-registered PRIMARY partition passed its validation (else nothing ships, full stop);
2. it beats `incumbent` by more than `MH25_MEANINGFUL_RMS_GAIN`;
3. ⭐ it beats `level_only` — the matched foil — by more than the same margin, so the gain is in the
   SHAPE of σ and not its LEVEL;
4. it beats the `flat_sigma` null and BOTH degenerates;
5. PBO < 0.2 over the 9-arm field;
6. DSR ≥ 0.95 under the MH2.1 Lock-3 fixed convention (per-FOLD observations, measured
   `trial_sharpes`, reference arm excluded from `V`, `n_trials` at full field size);
7. BH-FDR at q = 0.05 over the four real candidates, paired across folds;
8. the central-80% coverage FLOOR is not degraded.

Otherwise **INCUMBENT_STANDS**, and the null is classified with `cv_power.classify_null`. ⚠️ Per
MH2.2, a `classify_null` re-test trigger prescribing a field SMALLER than this declared 9-arm family
is SUSPECT ADVICE, not a remedy, and the harness flags it as such.

## LOCK 7 — the calibration split

The last **20%** of each fold's TRAINING rows by date, held out of the NGBoost fit, so every
recalibrator is fitted on HONEST out-of-sample residuals. This is load-bearing, not hygiene: fitting
a σ recalibration on in-sample residuals systematically SHRINKS σ — the exact opposite of what this
story set out to test. ⚠️ One consequence, stated in advance: the shared mean model therefore trains
on 80% of the fold rather than 100%, so absolute LEVELS are slightly pessimistic against the served
artifact. The handicap is identical across every arm, so the COMPARISON is exact (MH2.1 (c) — keep
the handicap identical, never post-hoc-trim it).

## LOCK 8 — candidate hyperparameters, fixed in advance

γ ∈ [0, 3]; ridge α = 1.0; degenerate multiplier 1.5; σ clamped to [0.3, 3.0] × the calibration
split's mean σ. No tuning pass — a two-parameter shape family does not warrant one, and an Optuna
sweep would inflate the field this study deliberately keeps small and coherent.

## LOCK 9 — NOT point-in-time

Inherited verbatim from MH2.1 Lock 4 and it still binds: the matrix reads each game's row as it
exists NOW, post-backfill and dense, so every number is a **CEILING**. It binds the LEVELS; the
arm-to-arm comparison is unaffected because every arm reads the identical matrix.

---

## Amendments after the fact — declared, and none of them can ship anything

1. **`incumbent_sigma_within_fold` (post-hoc stratifier).** Added after the pre-registered primary
   failed, to test whether the failure was a signal absence or an **era-mixing artifact** of pooling
   σ deciles across eleven seasons. Labelled POST-HOC everywhere it appears. It cannot produce a
   ship: the harness short-circuits the ship rule whenever the pre-registered primary is
   disqualified, whatever any other partition says.
2. **Per-fold validation tables.** The pre-registration asked for the pooled table only; the
   per-fold tables were added because only they separate "the signal is absent" from "the pooling
   mixes eras".
3. **`sigma_reproducibility` and `metric_divergence` diagnostics.** Both added after the run, both
   reported rather than gated. Neither enters any gate.
4. **`deflation_sensitivity`.** ⛔ **Reported, NOT applied.** The binding DSR stands exactly as
   pre-registered; the sensitivity exists so the record can say whether the failure was evidential
   or arithmetic, and so a successor can PRE-register the convention rather than discover it
   (MH2.2).

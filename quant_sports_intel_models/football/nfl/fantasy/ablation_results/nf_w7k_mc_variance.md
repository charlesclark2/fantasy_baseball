# NF-W7k — is QB's `dsr_ok` refusal reachable by a LOWER-VARIANCE design?

Generated 2026-08-19T05:38:04.042532+00:00 · position **QB** · 8 folds · 5 draw seeds × draw counts 4,000 and 1,000 · winner `zm_floor` vs best contest foil `mixall_learned`

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · research-only. ⛔ This story decides whether an expensive re-measurement is FUNDED — it certifies nothing and re-scores no other clause. The bar is UNCHANGED (`DSR_MIN` 0.95), the field is UNCHANGED (no trim — MH2.2), the folds are UNCHANGED.

## Verdict: **`MC_LEVER_EXHAUSTED`** · Phase B funded: **NO**

the CEILING deflated Sharpe — the gate with ALL Monte-Carlo error removed, which no draw count can beat — is 0.0 with CI95 upper end 0.0003, below the bar 0.95. ⇒ NO draw count clears `dsr_ok`: the DRAW-COUNT lever is EXHAUSTED, and ⛔ no draw / fold / season re-test trigger is published (NF-D18). ⚠️ SCOPE — this closes the DRAW lever, NOT every conceivable lower-variance design. The residual variance is what remains once draw noise is removed, and this design CANNOT split it further: across-fold varies the test ROWS and the SEASON together, so it mixes true season-to-season heterogeneity with finite-test-row sampling error. A row-count or sharper-metric lever is UNTESTED here, not refuted.

## The pre-registered decision rule, in order

| # | clause | measured | verdict |
|---|---|---|---|
| G0 | reproduction pin vs NF-W7f's STORED scores | max abs gap 0.000000000000 over 48 cells (tol 1e-09) | ✅ |
| G1 | the seed is live (across-seed sd > 0 everywhere) | 0 zero-spread cells | ✅ |
| G2 | σ²_MC scales as 1/draws | ratio 3.454 (nominal 4.0, band [2.0, 8.0]) | ✅ |
| G3 | the CEILING clears the bar | DSR_ceiling 0.0000, CI95 [0.0000, 0.0003] vs bar 0.95 | ❌ MC_LEVER_EXHAUSTED |

## §1 The variance decomposition — Monte-Carlo error vs everything else

> `σ²_MC` is the WITHIN-fold, ACROSS-seed variance of the paired delta at 4,000 draws — the error NF-W7f's published per-fold numbers actually carry. `σ_het` is what is LEFT once draw noise is removed. ⚠️ It is named `het` for brevity but it is **not purely season-to-season signal**: across-fold varies the test ROWS and the SEASON together, so this design cannot split true heterogeneity from finite-test-row sampling error. That does not affect the verdict — the ceiling removes `σ²_MC` and nothing else, which is exactly the draw-count question — but it does bound what the verdict CLOSES (see §4). ⭐ Common random numbers are preserved within a (fold, seed), exactly as NF-W7f does, so this is the Monte-Carlo error of the PAIRED quantity the gate reads — not the much larger and irrelevant error of either score alone.

| arm vs foil | mean δ | one-seed sd | σ_MC | σ_het | MC share of variance |
|---|---|---|---|---|---|
| `zm_conditional` | -0.04701 | 0.03430 | 0.00137 | 0.03427 | 0.0016 |
| `zm_floor` | 0.01806 | 0.01786 | 0.00099 | 0.01784 | 0.0031 |
| `zm_climatology` | -1.16881 | 0.10639 | 0.00305 | 0.10634 | 0.0008 |
| `zm_over` | -0.11902 | 0.04946 | 0.00132 | 0.04944 | 0.0007 |

- the winner `zm_floor`'s one-seed sd decomposes as σ_MC 0.00099 vs σ_het 0.01784 — MC share **0.0031**
- NF-W7f's published per-fold sd for this delta was 0.0182; measured here as 0.01786
- ⚠️ `σ_het` is reported SIGNED and never clamped: a negative estimate would say the observed fold spread is no larger than draw noise alone, and silently clamping it to zero would manufacture an infinite ceiling and a fake `FUND`.

### The 1/draws law, MEASURED rather than assumed

| arm | σ²_MC at 1,000 | σ²_MC at 4,000 | ratio | nominal | in band |
|---|---|---|---|---|---|
| `zm_conditional` | 5.749e-06 | 1.880e-06 | 3.058 | 4.0 | ✅ |
| `zm_floor` | 3.383e-06 | 9.796e-07 | 3.454 | 4.0 | ✅ |
| `zm_climatology` | 3.786e-05 | 9.288e-06 | 4.076 | 4.0 | ✅ |
| `zm_over` | 7.140e-06 | 1.748e-06 | 4.085 | 4.0 | ✅ |

### ⭐ How much Monte-Carlo error would the ceiling have NEEDED? (a sensitivity)

> Arithmetic on NF-W7f's ALREADY-PUBLISHED series — it measures nothing new. Its value is that it fixes the number the run has to beat BEFORE the run reports anything. ⚠️ Stated assumption: **one common absolute σ_MC across the declared arms** (the right first-order shape under common random numbers, but an assumption — the run measures each arm separately).

- a ceiling at the bar 0.95 would require Monte-Carlo error to be **0.9979** of the winner's per-fold variance (σ_MC ≈ 0.01813 against an observed one-seed sd of 0.01815)
- **MEASURED share: 0.0031**
- the best DSR anywhere on that sweep is 0.9512 — so even the most favourable assumed split only just reaches the bar 0.95

| assumed MC share of winner variance | winner Sharpe | `SR0` | DSR |
|---|---|---|---|
| 0.0000 | 1.013 | 5.482 | 0.0000 |
| 0.0072 | 1.017 | 5.483 | 0.0000 |
| 0.0272 | 1.027 | 5.487 | 0.0000 |
| 0.0599 | 1.045 | 5.494 | 0.0000 |
| 0.1054 | 1.071 | 5.504 | 0.0000 |
| 0.1637 | 1.108 | 5.517 | 0.0000 |
| 0.2348 | 1.158 | 5.536 | 0.0000 |
| 0.3186 | 1.227 | 5.560 | 0.0000 |
| 0.4152 | 1.325 | 5.594 | 0.0000 |
| 0.5246 | 1.470 | 5.644 | 0.0000 |
| 0.6467 | 1.705 | 5.725 | 0.0000 |
| 0.7817 | 2.168 | 5.885 | 0.0000 |
| 0.9294 | 3.812 | 6.484 | 0.0032 |

⭐ Read the `SR0` column: it climbs WITH the winner's Sharpe, because the winner is one of the four trials whose dispersion sets the bar. That is the whole reason the pre-registration made the ceiling bind over the MC-share proxy (§3.1) — a large MC share does not, on its own, imply a reachable gate.


## §2 The gate at every draw count — and at the CEILING

> ⭐ **THE WINNER IS A MEMBER OF ITS OWN TRIAL FIELD.** `SR0` is the deflation benchmark built from the DISPERSION of the four arms' Sharpes, and the winner is one of those four trials — so removing Monte-Carlo error raises the winner's Sharpe **and** `SR0` together. Whether the gap closes is arithmetic, which is why the pre-registration made the CEILING bind over the 'is the MC share large?' proxy (prereg §3.1).

| draws | winner Sharpe | `SR0` | DSR | clears 0.95? |
|---|---|---|---|---|
| observed (no-op identity) | 1.013 | 5.482 | 0.0000 | ❌ |
| 4,000 (reconstructed) | 1.030 | 5.510 | 0.0000 | ❌ |
| 16,000 draws | 1.031 | 5.512 | 0.0000 | ❌ |
| 64,000 draws | 1.031 | 5.513 | 0.0000 | ❌ |
| 256,000 draws | 1.031 | 5.513 | 0.0000 | ❌ |
| ceiling (∞ draws) | 1.031 | 5.513 | 0.0000 | ❌ |

- the **observed** row is the registered NO-OP identity (prereg §3.2): the projection at the observed sds must return NF-W7f's recorded DSR exactly, and it returns 0.0000
- CI95 on the ceiling DSR (folds resampled, 2000 usable resamples): [0.0000, 0.0003], median 0.0000
- the winner's projected Sharpe is asserted MONOTONE in the draw count — removing noise can only raise |SR|, so a violation would be a coding defect, not a finding

### Trial Sharpes at the ceiling (what sets the bar)

| arm | Sharpe observed | Sharpe at the ceiling |
|---|---|---|
| `zm_climatology` | -10.934 | -10.990 |
| `zm_conditional` | -1.347 | -1.366 |
| `zm_floor` | 1.013 | 1.031 |
| `zm_over` | -2.408 | -2.403 |

## §3 The null state, from the shared instrument

- state: **`DSR_UNREACHABLE`**
- reason: `nf_w7k_mc_variance|QB`: the winner's per-fold Sharpe 1.013 sits at or BELOW the 4-arm field's deflated benchmark SR0 5.482, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- re-test trigger: `field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)`
- `field_remedy_admissible`: `None`
- ⭐ read as a MACHINE FLAG, never the prose (MH2.7). ⛔ This story publishes NO draw / fold / season re-test trigger of its own: the ceiling is what no draw count can beat, so a trigger would be the NF-D18 misleading direction.


## §4 ⚠️ What this verdict closes, and what it does NOT

A ceiling argument is only as wide as the term it removes, and this one removes **draw noise and nothing else**. Stating the boundary explicitly so a future reader cannot over-read the verdict name:

**CLOSED — the draw-count lever.** More draws shrink `σ²_MC`; `σ²_MC` is 0.0031 of the winner's per-fold variance, and the ceiling that removes ALL of it still reads DSR 0.0000 against a bar of 0.95. No draw count clears `dsr_ok`. ⛔ This is a DETERMINISTIC bound, not a power statement — no `n` and no re-run overturns it, which is why no re-test trigger is published (NF-D18).

**NOT CLOSED — the row-count and metric levers.** `classify_null`'s own text names *"more rows per fold / a sharper metric"* alongside more draws. Those are DIFFERENT terms and this run did not test them: the residual `σ_het` mixes true season-to-season heterogeneity with finite-test-row sampling error, and separating them needs PER-ROW deltas, which this artifact does not store. ⇒ a successor wanting the row lever must capture per-row CRPS; it is UNTESTED here, ⛔ not refuted.

⚠️ And the row lever is not free even in principle: for a FIXED corpus, more rows per fold means FEWER folds, and fold count enters DSR through `√(n−1)`. It is a trade to be measured, not a lever to be assumed.

## ⭐ Flagged for a 2nd reader (governance)

A DSR gate re-read is governance-adjacent. Protections, all registered BEFORE any score existed (prereg §5): the bar is unchanged at `DSR_MIN = 0.95`; the field is unchanged (no post-hoc trim — MH2.2); the folds are unchanged; the seeds, both draw counts, the decision rule, the `{16,000 · 64,000 · 256,000}` ladder and its cap were all fixed in advance; and the only admissible ship path runs through a FULL-gate Phase B, never through this story. **`MC_LEVER_EXHAUSTED` closes a lever; it does not weaken a bar.**

## Promote blockers

- NF-W7k decides whether an expensive re-measurement is FUNDED. It certifies nothing, re-scores no other clause and does not re-open NF-W7f's or NF-W7j's verdicts
- the certification bar is UNCHANGED — the full NF-W7f gate including `dsr_ok` stands (E2.1-r); WR and TE cleared it and RB was held to it
- the field is UNCHANGED — no arm was trimmed after scoring (MH2.2)
- ⛔ QB ONLY. Nothing here certifies RB / WR / TE, and NF-W7c §4's rule still binds: a per-position-certified distribution may not feed a CROSS-POSITION ranking
- NF-W7f's and NF-W7j's promote blockers are inherited in full

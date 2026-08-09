# DSR-CONV — characterization: degenerate arithmetic vs the fold count

⛔ **SYNTHETIC FIELDS WITH A PLANTED EFFECT. NOT A RE-VERDICT ON ANY RECORDED STORY.** Every number below is a property of the DSR estimator under a known data-generating process. No recorded null is re-scored here, and none may be re-read against this memo — the DSR-CONV convention is FORWARD-ONLY (MH2 §a / E2.1-r: a gate re-read against a result already seen is laundering).

Design: 300 replicates per cell · 5 genuine arms (1 winner with a planted per-fold Sharpe + 4 candidates dispersing at SD 0.15) · 2 pre-registered degenerates when extremity > 0 · gate `DSR ≥ 0.95`. `n_trials` is the FULL field under both conventions; only `V` differs.

**Extremity** = the degenerate's per-fold skill |Sharpe| (how badly it loses ÷ how consistently). `extremity 0.0` is the CONTROL — no degenerate in the field, so the two conventions coincide by construction and any gap there would be a bug.


## 1. Clearance rate at the 0.95 gate, both conventions

A cell reads: of the replicates where a REAL effect of that size was planted, what fraction cleared the gate. `Δ` is the fraction of runs that degenerate-exclusion rescues.


### planted per-fold Sharpe = 0.7

| folds | ext 0.0 | ext 1.0 | ext 3.0 | ext 6.0 | ext 10.0 |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.04 → 0.04 (+0.00) | 0.03 → 0.03 (+0.00) | 0.00 → 0.04 (+0.03) | 0.00 → 0.03 (+0.03) | 0.00 → 0.04 (+0.04) |
| 4 | 0.03 → 0.03 (+0.00) | 0.01 → 0.03 (+0.01) | 0.00 → 0.02 (+0.02) | 0.00 → 0.03 (+0.03) | 0.00 → 0.03 (+0.03) |
| 5 | 0.02 → 0.02 (+0.00) | 0.00 → 0.01 (+0.01) | 0.00 → 0.01 (+0.01) | 0.00 → 0.01 (+0.01) | 0.00 → 0.01 (+0.01) |
| 6 | 0.04 → 0.04 (+0.00) | 0.01 → 0.02 (+0.01) | 0.00 → 0.01 (+0.01) | 0.00 → 0.01 (+0.01) | 0.00 → 0.02 (+0.02) |
| 8 | 0.02 → 0.02 (+0.00) | 0.00 → 0.01 (+0.01) | 0.00 → 0.01 (+0.01) | 0.00 → 0.02 (+0.02) | 0.00 → 0.02 (+0.02) |
| 11 | 0.04 → 0.04 (+0.00) | 0.00 → 0.01 (+0.01) | 0.00 → 0.02 (+0.02) | 0.00 → 0.03 (+0.03) | 0.00 → 0.02 (+0.02) |
| 13 | 0.03 → 0.03 (+0.00) | 0.00 → 0.01 (+0.01) | 0.00 → 0.02 (+0.02) | 0.00 → 0.02 (+0.02) | 0.00 → 0.03 (+0.03) |

### planted per-fold Sharpe = 1.5

| folds | ext 0.0 | ext 1.0 | ext 3.0 | ext 6.0 | ext 10.0 |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.13 → 0.13 (+0.00) | 0.07 → 0.10 (+0.03) | 0.03 → 0.09 (+0.07) | 0.01 → 0.07 (+0.06) | 0.00 → 0.09 (+0.09) |
| 4 | 0.13 → 0.13 (+0.00) | 0.03 → 0.06 (+0.03) | 0.00 → 0.06 (+0.06) | 0.00 → 0.07 (+0.07) | 0.00 → 0.07 (+0.07) |
| 5 | 0.12 → 0.12 (+0.00) | 0.04 → 0.07 (+0.03) | 0.00 → 0.06 (+0.05) | 0.00 → 0.06 (+0.06) | 0.00 → 0.05 (+0.05) |
| 6 | 0.15 → 0.15 (+0.00) | 0.05 → 0.09 (+0.04) | 0.00 → 0.06 (+0.06) | 0.00 → 0.09 (+0.09) | 0.00 → 0.09 (+0.09) |
| 8 | 0.17 → 0.17 (+0.00) | 0.04 → 0.10 (+0.05) | 0.00 → 0.08 (+0.08) | 0.00 → 0.08 (+0.08) | 0.00 → 0.11 (+0.11) |
| 11 | 0.28 → 0.28 (+0.00) | 0.06 → 0.14 (+0.09) | 0.00 → 0.15 (+0.15) | 0.00 → 0.17 (+0.17) | 0.00 → 0.15 (+0.15) |
| 13 | 0.36 → 0.36 (+0.00) | 0.05 → 0.17 (+0.12) | 0.00 → 0.16 (+0.15) | 0.00 → 0.18 (+0.18) | 0.00 → 0.18 (+0.18) |

### planted per-fold Sharpe = 3.0

| folds | ext 0.0 | ext 1.0 | ext 3.0 | ext 6.0 | ext 10.0 |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.27 → 0.27 (+0.00) | 0.18 → 0.16 (-0.02) | 0.05 → 0.12 (+0.07) | 0.01 → 0.16 (+0.16) | 0.00 → 0.18 (+0.18) |
| 4 | 0.33 → 0.33 (+0.00) | 0.16 → 0.15 (-0.02) | 0.02 → 0.17 (+0.14) | 0.01 → 0.18 (+0.17) | 0.00 → 0.11 (+0.11) |
| 5 | 0.39 → 0.39 (+0.00) | 0.14 → 0.16 (+0.02) | 0.01 → 0.19 (+0.18) | 0.00 → 0.13 (+0.13) | 0.00 → 0.19 (+0.19) |
| 6 | 0.41 → 0.41 (+0.00) | 0.18 → 0.19 (+0.01) | 0.02 → 0.24 (+0.22) | 0.00 → 0.22 (+0.22) | 0.00 → 0.22 (+0.22) |
| 8 | 0.52 → 0.52 (+0.00) | 0.28 → 0.31 (+0.02) | 0.02 → 0.29 (+0.27) | 0.00 → 0.29 (+0.29) | 0.00 → 0.31 (+0.31) |
| 11 | 0.71 → 0.71 (+0.00) | 0.43 → 0.48 (+0.05) | 0.02 → 0.44 (+0.42) | 0.00 → 0.41 (+0.41) | 0.00 → 0.45 (+0.45) |
| 13 | 0.83 → 0.83 (+0.00) | 0.45 → 0.54 (+0.08) | 0.01 → 0.52 (+0.51) | 0.00 → 0.53 (+0.53) | 0.00 → 0.51 (+0.51) |

### planted per-fold Sharpe = 5.0

| folds | ext 0.0 | ext 1.0 | ext 3.0 | ext 6.0 | ext 10.0 |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.34 → 0.34 (+0.00) | 0.27 → 0.17 (-0.10) | 0.10 → 0.20 (+0.10) | 0.02 → 0.19 (+0.17) | 0.01 → 0.15 (+0.15) |
| 4 | 0.37 → 0.37 (+0.00) | 0.27 → 0.19 (-0.08) | 0.10 → 0.24 (+0.14) | 0.03 → 0.20 (+0.17) | 0.01 → 0.19 (+0.18) |
| 5 | 0.49 → 0.49 (+0.00) | 0.35 → 0.26 (-0.09) | 0.10 → 0.26 (+0.15) | 0.01 → 0.23 (+0.22) | 0.00 → 0.29 (+0.29) |
| 6 | 0.57 → 0.57 (+0.00) | 0.38 → 0.32 (-0.07) | 0.09 → 0.28 (+0.20) | 0.02 → 0.26 (+0.24) | 0.00 → 0.29 (+0.28) |
| 8 | 0.66 → 0.66 (+0.00) | 0.60 → 0.49 (-0.11) | 0.12 → 0.45 (+0.33) | 0.01 → 0.48 (+0.48) | 0.00 → 0.42 (+0.42) |
| 11 | 0.85 → 0.85 (+0.00) | 0.76 → 0.60 (-0.15) | 0.16 → 0.60 (+0.44) | 0.00 → 0.61 (+0.61) | 0.00 → 0.62 (+0.62) |
| 13 | 0.89 → 0.89 (+0.00) | 0.87 → 0.76 (-0.11) | 0.18 → 0.71 (+0.53) | 0.00 → 0.78 (+0.78) | 0.00 → 0.72 (+0.72) |

## 2. What exclusion does to the BAR itself

`SR0 = √V·z(N)`. Exclusion changes `V` only; `n_trials` (hence `z(N)`) is untouched. **`req SR`** is the deterministic per-fold Sharpe a winner must actually POST to clear the gate at that `V` and fold count — the difficulty in the unit the gate uses, free of any planted effect (MH2 Lock 5: state the bar in the unit the gate uses).

| folds | extremity | median V (with) | median V (excl) | V inflation × | SR0 (with) | SR0 (excl) | req SR (with) | req SR (excl) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 0.0 | 1.4359 | 1.4359 | 1.0× | 1.558 | 1.558 | 9.270 | 9.270 |
| 3 | 1.0 | 2.2541 | 1.5275 | 1.5× | 2.190 | 1.803 | 12.699 | 10.590 |
| 3 | 3.0 | 7.8233 | 1.7968 | 4.4× | 4.081 | 1.956 | 23.181 | 11.418 |
| 3 | 6.0 | 22.9358 | 2.0344 | 11.3× | 6.987 | 2.081 | 39.467 | 12.101 |
| 3 | 10.0 | 51.2030 | 1.4577 | 35.1× | 10.440 | 1.762 | 58.872 | 10.365 |
| 4 | 0.0 | 0.9788 | 0.9788 | 1.0× | 1.286 | 1.286 | 4.372 | 4.372 |
| 4 | 1.0 | 1.6037 | 0.9803 | 1.6× | 1.848 | 1.445 | 5.963 | 4.813 |
| 4 | 3.0 | 5.1971 | 0.9626 | 5.4× | 3.326 | 1.431 | 10.323 | 4.777 |
| 4 | 6.0 | 15.7588 | 1.0414 | 15.1× | 5.792 | 1.489 | 17.747 | 4.938 |
| 4 | 10.0 | 46.3219 | 1.1983 | 38.7× | 9.930 | 1.597 | 30.297 | 5.245 |
| 5 | 0.0 | 0.7578 | 0.7578 | 1.0× | 1.132 | 1.132 | 3.128 | 3.128 |
| 5 | 1.0 | 1.3041 | 0.7806 | 1.7× | 1.666 | 1.289 | 4.297 | 3.466 |
| 5 | 3.0 | 4.7008 | 0.8585 | 5.5× | 3.163 | 1.352 | 7.738 | 3.603 |
| 5 | 6.0 | 14.0777 | 0.8338 | 16.9× | 5.474 | 1.332 | 13.187 | 3.560 |
| 5 | 10.0 | 36.2181 | 0.8216 | 44.1× | 8.781 | 1.322 | 21.049 | 3.539 |
| 6 | 0.0 | 0.7522 | 0.7522 | 1.0× | 1.128 | 1.128 | 2.724 | 2.724 |
| 6 | 1.0 | 1.2150 | 0.7372 | 1.6× | 1.608 | 1.253 | 3.639 | 2.958 |
| 6 | 3.0 | 3.9172 | 0.7299 | 5.4× | 2.888 | 1.246 | 6.191 | 2.946 |
| 6 | 6.0 | 13.4947 | 0.7658 | 17.6× | 5.360 | 1.277 | 11.265 | 3.004 |
| 6 | 10.0 | 36.1048 | 0.7286 | 49.6× | 8.767 | 1.245 | 18.329 | 2.944 |
| 8 | 0.0 | 0.6264 | 0.6264 | 1.0× | 1.029 | 1.029 | 2.166 | 2.166 |
| 8 | 1.0 | 1.0257 | 0.6428 | 1.6× | 1.478 | 1.170 | 2.893 | 2.391 |
| 8 | 3.0 | 3.7167 | 0.7019 | 5.3× | 2.813 | 1.222 | 5.168 | 2.476 |
| 8 | 6.0 | 11.8408 | 0.6237 | 19.0× | 5.021 | 1.152 | 9.045 | 2.363 |
| 8 | 10.0 | 30.3455 | 0.7166 | 42.3× | 8.037 | 1.235 | 14.396 | 2.496 |
| 11 | 0.0 | 0.6118 | 0.6118 | 1.0× | 1.017 | 1.017 | 1.883 | 1.883 |
| 11 | 1.0 | 0.9562 | 0.6222 | 1.5× | 1.427 | 1.151 | 2.475 | 2.074 |
| 11 | 3.0 | 3.4032 | 0.5961 | 5.7× | 2.692 | 1.126 | 4.387 | 2.039 |
| 11 | 6.0 | 11.2816 | 0.6228 | 18.1× | 4.901 | 1.151 | 7.825 | 2.075 |
| 11 | 10.0 | 30.3770 | 0.5633 | 53.9× | 8.041 | 1.095 | 12.765 | 1.994 |
| 13 | 0.0 | 0.5782 | 0.5782 | 1.0× | 0.989 | 0.989 | 1.742 | 1.742 |
| 13 | 1.0 | 0.8983 | 0.5783 | 1.6× | 1.383 | 1.109 | 2.285 | 1.906 |
| 13 | 3.0 | 3.3500 | 0.5690 | 5.9× | 2.670 | 1.101 | 4.139 | 1.894 |
| 13 | 6.0 | 11.3051 | 0.5375 | 21.0× | 4.906 | 1.070 | 7.453 | 1.852 |
| 13 | 10.0 | 28.8381 | 0.5992 | 48.1× | 7.835 | 1.129 | 11.838 | 1.934 |

## 3. The part exclusion CANNOT fix — the structural fold-count penalty

Two DIFFERENT structural facts get conflated here, and only one of them binds at this gate. Both are independent of `V`, so neither is touched by DSR-CONV.

**(a) The ceiling.** `dsr_ceiling(n)` is the largest DSR attainable at `n` observations **at any effect size whatsoever** (the statistic carries `√(n_obs − 1)`). ⚠️ Against the 0.95 gate it does NOT bind anywhere in this grid — even 3 folds ceilings at 0.9772 — so 'the ceiling blocked it' is the WRONG explanation for a small-fold DSR failure at this gate, and would be a fabricated cause if quoted as one. It binds only against a stricter gate.

**(b) The required Sharpe, which DOES bind.** The same `√(n_obs − 1)` scaling means the Sharpe a winner must POST to reach 0.95 explodes as folds fall — at a FIXED, clean `V`. This is the real small-fold penalty.

| folds | dsr_ceiling | ceiling ≥ 0.95 gate? | median req SR at clean V |
|---:|---:|:--|---:|
| 3 | 0.9772 | ✅ does not bind | 13.74 |
| 4 | 0.9928 | ✅ does not bind | 6.09 |
| 5 | 0.9977 | ✅ does not bind | 4.32 |
| 6 | 0.9992 | ✅ does not bind | 3.67 |
| 8 | 0.9999 | ✅ does not bind | 3.08 |
| 11 | 1.0000 | ✅ does not bind | 2.58 |
| 13 | 1.0000 | ✅ does not bind | 2.42 |

## 4. The read

- **Control holds — the change is inert when nothing is declared.** Across every `extremity 0.0` cell the two conventions differ by at most **0.0000** in clearance. With no degenerate declared they are the SAME statistic, which is what makes the convention safe for a caller that has not been updated.
- **⭐ THE EXCLUSION IS NOT MONOTONE, AND THAT IS THE MOST IMPORTANT LINE HERE.** It is a rescue only when the declared arm is GENUINELY far out. At extremity ≥ 3 it moves clearance by a median **+0.145**. At extremity 1.0 — a 'loser' that still sits INSIDE the real arms' spread — the median move is only **+0.008** and it goes the WRONG way in **9/28** cells, as far as **-0.153**. The mechanism is plain: `V` is a SAMPLE variance, so dropping points that sit near the mean INCREASES the variance of what remains. ⇒ the convention is not a free pass in either direction, and an arm may be declared a degenerate only because the DESIGN made it one — never because excluding it helps.
- **The arithmetic penalty scales with EXTREMITY, essentially flat in fold count.** §2's `V` inflation reaches ~35–54× at extremity 10 at every fold count. So degenerate-exclusion is a FIELD-COMPOSITION fix, not a small-fold fix — it just bites hardest wherever the margin was thinnest.
- **⛔ It does NOT resolve the small-fold difficulty, and the numbers say so plainly.** Even on a fully CLEAN `V`, the Sharpe a winner must post is a median **13.74** at 3 folds against **2.42** at 13. Correspondingly, the rescue at extremity ≥ 3 is a median **+0.078** at ≤4 folds but **+0.298** at ≥11. The residue at 3–4 folds is STRUCTURAL — the `√(n_obs − 1)` scaling in the required Sharpe, §3(b) — and no `V` convention touches it. ⚠️ It is NOT the `dsr_ceiling`, which does NOT bind at this gate (§3(a)); attributing a small-fold DSR failure to the ceiling would be a fabricated cause.
- **Therefore, as an input to a future reading decision:** removing the degenerates from `V` fixes a real and sometimes large arithmetic defect, but a leg at 3–4 folds remains hard for reasons that have nothing to do with field composition. Any residual small-fold difficulty observed AFTER this change should be attributed to the fold count, not re-litigated as a field-composition problem.

---
*Generated by `betting_ml/scripts/dsr_conv_characterization.py` (deterministic seeds; re-run reproduces byte-for-byte).*

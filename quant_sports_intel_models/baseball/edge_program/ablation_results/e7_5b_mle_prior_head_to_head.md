# MLB Edge-E7.5b — re-deriving the SERVED rookie prior from the E7.12 MLE, behind E7.5's own held-out gate

**generated:** 2026-08-01T23:34:37.625186+00:00

- **challenger projections:** `s3://baseball-betting-ml-artifacts/baseball/milb/derived/mle_projections`  (model_version `milb_mle_v2_parkctx`, 12423 rows)
- **incumbent projections:** `quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_projections.parquet`  (model_version `milb_mle_v1`, 12398 rows)
- **currently-served prior:** `/tmp/milb_mle_prior_pre_e7_5b.parquet` (6365 batters)
- **label substrate:** `quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_graduated_pairs.parquet`

> 🚨 **This is the BETTING prior, not the draft board.** The board reads `mle_projections` directly and has carried the E7.12 slice-1 model since it published; the SERVED path reads a separately-recalibrated parquet (`milb_mle_prior` → `eb_batter_posteriors_raw` → `avg_eb_*` → the served `run_diff` / `pre_lineup` contract) that is still derived from `milb_mle_v1`. E7.5b is the sanctioned, gated way to close that divergence for BATTERS. `best_alpha = 0` — a cold-start prior, never a market bet.

## 0. Pre-registration (the gate, fixed before the head-to-head was run)

The E7.12 gain is a **TRANSLATION-MAE** gain. Rookie-prior CALIBRATION is a different objective, so a translation win need not survive here — **a null is a valid and expected outcome and is not shipped.** The incumbent already beats the generic prior, so *beating generic is not evidence for a swap*; the contest below is challenger vs **what is serving today**.

A metric SHIPS only if **every** condition holds; otherwise it keeps the served incumbent verbatim.

| # | condition | why |
|:--|:--|:--|
| 1 | challenger NLL < incumbent NLL | the primary proper score (calibration × sharpness) |
| 2 | challenger CRPS ≤ incumbent CRPS | E7.5's own `mle_wins` pair — CRPS isolates the MEAN, so a win on NLL alone could be an sd artifact |
| 3 | challenger wins ≥60% of evaluable cohorts | E7.12 slice 1's fold-rate bar, verbatim — a pooled mean cannot tell *systematically better* from *won by a hair* |
| 4 | one-sided paired p < 0.10 on the per-cohort NLL delta | the same paired instrument, same α |
| 5 | **BH-FDR@0.10 across the three metrics** | three metrics is a three-test family (NF-D15) |
| 6 | challenger `cov68 ≥ 0.61` **and** `cov90 ≥ 0.83` | ⭐ the named failure mode: a prior that gets SHARPER without getting better CALIBRATED. A one-sided **FLOOR** — never a target (E2.1-r) |
| 7 | both degenerate ceilings LOSE | generic population prior + the challenger's own means PERMUTED within the held-out cohort (same marginal, pairing destroyed) |
| 8 | both per-form oracle floors HOLD | each arm floored by the peeking version of **its own** form — a single shared ceiling would veto a legitimately-better arm (NF-D16 (g‴)) |

**Disclosure.** Conditions 1–8 are the E7.5 / E7.12-slice-1 house gate transplanted verbatim, not tuned to this result. They were fixed after a *comparability* check (below) that showed the sign of the per-metric deltas but none of the paired statistics, anchors or coverage the gate turns on.

### Comparability — the archived E7.5 numbers are NOT the baseline

The E7.5 report on file was generated 2026-07-26 against a `mle_graduated_pairs` substrate that has since gained labelled graduates (its ablation scored **n=534 over 10 cohorts**; re-running the SAME `milb_mle_v1` model on today's substrate scores **n=538**). Quoting the archived numbers as the bar would compare two models over two different populations — the E7.12 `cache_is_current` lesson. **Both arms below are re-run on today's substrate, on the matched intersection of labelled rows.**

## 1. Head-to-head — purged leave-one-debut-cohort-out, matched population

| metric   |   n_scored |   n_cohorts |   chal_nll |   inc_nll |   chal_crps |   inc_crps |   chal_mae |   inc_mae |   chal_cov68 |   inc_cov68 |   chal_cov90 |   inc_cov90 |   fold_win_rate |   p_one_sided | BH-FDR@0.10   |
|:---------|-----------:|------------:|-----------:|----------:|------------:|-----------:|-----------:|----------:|-------------:|------------:|-------------:|------------:|----------------:|--------------:|:--------------|
| k_pct    |        538 |          10 |   -1.67321 |  -1.68641 |    0.025487 |   0.025324 |   0.035992 |  0.036144 |       0.6914 |      0.697  |       0.9126 |      0.9145 |             0.3 |       0.7263  | False         |
| bb_pct   |        538 |          10 |   -2.44029 |  -2.37659 |    0.011807 |   0.012633 |   0.01671  |  0.018079 |       0.7156 |      0.6989 |       0.9349 |      0.9238 |             0.9 |       0.01377 | True          |
| iso      |        538 |          10 |   -1.64577 |  -1.57371 |    0.025996 |   0.028157 |   0.036977 |  0.04015  |       0.7305 |      0.7063 |       0.9294 |      0.9294 |             0.9 |       0.0043  | True          |

Every arm is **self-calibrated on its OWN prior-cohort residual sd**, so the comparison is calibration × sharpness rather than an sd handicap. `n_scored` is the MATCHED intersection — both arms are scored on byte-identical rows against a byte-identical realized label.

## 2. Anchors — a degenerate that must LOSE and a peeking floor that must WIN

| metric   |   challenger_nll |   generic_degenerate |   permuted_degenerate |   oracle_challenger (floor) |   oracle_incumbent (floor) | degenerates_lose   | oracle_floor_holds   |
|:---------|-----------------:|---------------------:|----------------------:|----------------------------:|---------------------------:|:-------------------|:---------------------|
| k_pct    |         -1.67321 |             -1.36103 |              -0.9828  |                    -1.71139 |                   -1.71632 | True               | True                 |
| bb_pct   |         -2.44029 |             -2.24365 |              -2.00627 |                    -2.44401 |                   -2.41614 | True               | True                 |
| iso      |         -1.64577 |             -1.50458 |              -1.32027 |                    -1.68017 |                   -1.65076 | True               | True                 |

- **Degenerate ceilings** — the generic population prior, and the challenger's own means PERMUTED within the held-out cohort. The permutation preserves the marginal distribution EXACTLY and destroys only the per-player pairing, so it is the cleanest available statement of *is there per-player content here at all*, and it is well-posed at any n (unlike a fitted oracle, NF1.7 (b)).
- **Peeking floors are PER FORM** — each arm is floored by itself shifted by the held-out cohort's own mean residual. Flooring both arms on ONE ceiling would veto a legitimately-better arm as a false metric inversion (NF-D16 (g‴)). An arm beating its own oracle is mathematically impossible ⇒ the tell that the score is inverted, not a win.

## 3. Per-cohort paired NLL deltas (incumbent − challenger; >0 ⇒ the challenger is better)

|    |    k_pct |   bb_pct |      iso |
|---:|---------:|---------:|---------:|
|  0 | -0.03596 |  0.0114  |  0.03126 |
|  1 | -0.01155 |  0.023   | -0.00229 |
|  2 | -0.03164 |  0.0186  |  0.03483 |
|  3 | -0.03122 |  0.00542 |  0.05444 |
|  4 | -0.11972 |  0.10051 |  0.08028 |
|  5 |  0.03373 |  0.05282 |  0.09434 |
|  6 | -0.00035 |  0.19741 |  0.20616 |
|  7 | -0.07695 |  0.13203 |  0.09824 |
|  8 |  0.0727  |  0.02653 |  0.03024 |
|  9 |  0.07822 | -0.01205 |  0.01161 |

## 4. σ_resid / κ movement — is it SHARPER, and did it stay CALIBRATED?

| metric   |   sigma_incumbent |   sigma_challenger |   sigma_delta_% |   cov68_incumbent |   cov68_challenger |   cov90_incumbent |   cov90_challenger |
|:---------|------------------:|-------------------:|----------------:|------------------:|-------------------:|------------------:|-------------------:|
| k_pct    |          0.044859 |           0.044539 |          -0.713 |            0.6805 |             0.6739 |            0.9035 |             0.9002 |
| bb_pct   |          0.022222 |           0.021457 |          -3.443 |            0.6656 |             0.6889 |            0.9068 |             0.9185 |
| iso      |          0.048389 |           0.046649 |          -3.597 |            0.6722 |             0.6889 |            0.8935 |             0.8985 |

A **narrower σ_resid is a STRONGER prior** — for K%/BB% it raises the Beta pseudo-count κ = m(1−m)/σ² − 1 (the prior's equivalent MLB-PA weight), for ISO it raises κ_iso = 0.25/σ². So a sharpening that is NOT accompanied by held-out coverage staying at nominal would pull a rookie's line harder toward a projection that has not earned it. That is exactly what condition 6 gates, and why the coverage figure is read as a floor rather than minimised toward a target.

## 5. Verdict — per metric, not all-or-nothing

| metric   | beats_on_nll   | beats_on_crps   | fold_win_rate>=0.60   | p_one_sided<0.1   | coverage_floor_holds   | degenerate_ceilings_lose   | oracle_floor_holds   | BH-FDR@0.10   | VERDICT                    |
|:---------|:---------------|:----------------|:----------------------|:------------------|:-----------------------|:---------------------------|:---------------------|:--------------|:---------------------------|
| k_pct    | False          | False           | False                 | False             | True                   | True                       | True                 | False         | HOLD (served v1 verbatim)  |
| bb_pct   | True           | True            | True                  | True              | True                   | True                       | True                 | True          | SHIP (milb_mle_v2_parkctx) |
| iso      | True           | True            | True                  | True              | True                   | True                       | True                 | True          | SHIP (milb_mle_v2_parkctx) |

- **k_pct** — 🟡 **HOLD — the served `milb_mle_v1` prior is kept VERBATIM.** Failed: beats_on_nll, beats_on_crps, fold_win_rate>=0.60, p_one_sided<0.1, BH-FDR@0.10. NLL -1.67321 vs -1.68641, CRPS 0.025487 vs 0.025324, MAE 0.035992 vs 0.036144; 30% of 10 cohorts, one-sided p=0.7263.
- **bb_pct** — ✅ **SHIP.** NLL -2.44029 vs -2.37659, CRPS 0.011807 vs 0.012633, MAE 0.016710 vs 0.018079; 90% of 10 cohorts, one-sided p=0.0138, BH-FDR@0.10 True.
- **iso** — ✅ **SHIP.** NLL -1.64577 vs -1.57371, CRPS 0.025996 vs 0.028157, MAE 0.036977 vs 0.040150; 90% of 10 cohorts, one-sided p=0.0043, BH-FDR@0.10 True.

> 🔎 **Reading the `k_pct` hold honestly.** The mean per-cohort NLL delta is **-0.01227** — the WRONG side of zero — and the challenger wins **3/10** cohorts. This is a LOSS/TIE, not an under-powered win: more debut cohorts would not turn it, so it is not a candidate for a scheduled re-validation. Note the challenger's MAE **is** slightly better (0.035992 vs 0.036144) — the E7.12 translation-MAE gain is directionally present, it simply does not convert into better PRICING. That is the story's whole premise, measured rather than assumed: a translation-MAE objective and a rookie-prior CALIBRATION objective are not the same objective, and a win on one does not transfer to the other (the repo's pricing-optimal ≠ discrimination-optimal rule, facing the other way).

## 6. What is written — and how far the SERVED numbers actually move

| served column      |   mean_abs_delta |   p95_abs_delta |   max_abs_delta |   n_moved |
|:-------------------|-----------------:|----------------:|----------------:|----------:|
| mle_k_pct          |         0        |        0        |        0        |         0 |
| k_pct_prior_kappa  |         0        |        0        |        0        |         0 |
| mle_bb_pct         |         0.005309 |        0.012827 |        0.042667 |      6365 |
| bb_pct_prior_kappa |         9.20164  |       22.6155   |       72.644    |      6365 |
| mle_iso            |         0.009389 |        0.024677 |        0.078253 |      6365 |
| iso_prior_sd       |         0.000834 |        0.000834 |        0.000834 |      6365 |

Deltas are against the parquet serving today, over the batters both tables share. A held-back metric reads **0.0 across the board** — that is the verbatim guarantee, measured on the final table rather than asserted. For a shipped metric this is the magnitude of change entering `eb_batter_posteriors_raw`; it is diluted further downstream, because the prior only dominates at low MLB PA and the Beta-Binomial / pseudo-count update hands over to the rookie's own observed line as PA accrues.

### Provenance and row spine

- **Shipped metrics:** ['bb_pct', 'iso'] — re-derived from the challenger MLE.
- **Held back:** ['k_pct'] — columns copied VERBATIM from the parquet serving today, so those served numbers are byte-identical before and after.
- Row spine = the challenger's batter set (6376 batters, 11 new vs the 6365 serving today). A batter who carries a served prior but is absent from the re-derived table would silently LOSE it — that is asserted, not assumed, and the write refuses if it happens.
- Per-metric provenance is carried in `<metric>_source` columns. They are inert to the dbt consumer (`eb_batter_posteriors_raw` selects named columns) and exist so a future audit can tell which arm each served number came from.

## 7. Limitations

- **The eval population is graduated players** (they reached the E7.3 MLB-PA label floor) — self-selected, and inherited from E7.3/E7.5. Stated, not corrected.
- **10 evaluable debut cohorts is a weak instrument.** The paired p is reported for what it is; the fold win rate and the anchors carry more of the load than the p-value does.
- **PBO/DSR are not reported and would be meaningless here**: this is a two-arm pre-specified contest, not a search over a candidate field, so there is no in-sample selection to deflate. The multiplicity that DOES exist — three metrics — is handled by BH-FDR (condition 5).
- **A held-back metric on a batter whose highest reached level moved between the two projection sets** keeps the served value, which was translated at the incumbent's level. `mle_level` describes the challenger. Cosmetic (the dbt consumer never reads `mle_level`), stated for audit.
- **`best_alpha = 0`** — a cold-start rookie prior, never a market bet.


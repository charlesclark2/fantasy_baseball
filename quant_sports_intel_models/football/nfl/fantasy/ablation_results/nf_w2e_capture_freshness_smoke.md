# NF-W2e — is NF-W2d's 2025 attenuation caused by CAPTURE FRESHNESS?

**Generated:** 2026-08-10T00:06:33+00:00 · folds scored: 4 · capture-era (ACTIVE) folds: 2 · rows 84553

> ⛔ **This study CERTIFIES NOTHING, by design.** `best_alpha = 0`, deploy-held. The consumption rule can only act on capture-era rows, so the active-fold count is a DESIGN quantity — see the power ceiling below. The primary read is a week-CLUSTERED row-level paired delta, never a fold-level gate.

## Power ceiling (computed, not asserted)

```json
{
  "active_folds": 2,
  "fold_clause_attainable": false,
  "fold_clause_wins_required": null,
  "pbo_evaluable": false,
  "sign_test_floor": 0.25,
  "dsr_ceiling": 0.9214,
  "dsr_gate": 0.95,
  "folds_for_sign_certifiability": 4,
  "verdict": "NO_CERTIFICATION_POSSIBLE",
  "reason": "the mechanism can only act on capture-era rows, so the active-fold count is a DESIGN quantity: no effect of any size could clear these gates. The re-test trigger is calendar-bound \u2014 the capture era gains ~2 folds per season of NF-W0a forward capture, so PBO becomes evaluable at 4 folds (end of 2026)."
}
```

## Controls

- **Mechanical: the ladder is inert before 2025** — `PASS` {"passes": true, "legacy_rows": 75865, "cells_compared": 28, "differences": []}
- **The scored population is identical across rungs** — `PASS` {"passes": true, "per_rung": {"inj_latest": {"rows": 84553, "observed_rows": 84105}, "inj_fresh1d": {"rows": 84553, "observed_rows": 84105}, "inj_freshest": {"rows": 84553, "observed_rows": 84105}}, "mismatched_rungs": []}
- **Rows are aligned across rungs (paired deltas are valid)** — `PASS` {"passes": true, "rows": 84553, "misaligned_rungs": []}
- **Measured: the rungs tie on the registered legacy folds** — `PASS` {"passes": true, "folds": ["2024H1", "2024H2"], "comparisons": 16, "tolerance": 1e-09, "max_abs_delta": 0.0, "differences": []}

## Stratifier validation (published BEFORE any lift — MH2.1)

**VALIDATED** — corrected rank corr 0.289 (p=0.0), change rate 0.161 (≤1 d) vs 0.3632 (>1 d).

⚠️ The FIRST cut read rank corr -0.0026 (p=0.947432) — an artifact: nfl.com publishes practice-only rows with a NULL report_status, so a pair crossing between a designation-publishing source and a practice-publishing one scores as a 'change' that is a SOURCE-FORMAT difference, not a designation change (286 pairs dropped).

| bin    |   n |   change_rate |     se |
|:-------|----:|--------------:|-------:|
| <0.5d  |  52 |        0.0385 | 0.0267 |
| 0.5-1d |  66 |        0.2576 | 0.0538 |
| 1-2d   |  84 |        0.3333 | 0.0514 |
| 2-3d   |  10 |        0.2    | 0.1265 |
| >3d    | 129 |        0.3953 | 0.043  |

## Carry-over census + ladder activity (NF-D20)

{"state": "OK", "listed_rows": 1343, "superseded_rows": 487, "superseded_share": 0.3626, "carryover_gap_days": {"50%": 1.653, "90%": 4.078, "max": 6.144}, "note": "structurally impossible in the legacy era (one nflverse report per player-week), so this is a capture-regime property, not a defect"}

|              |   listed_capture_era_rows | by_position                                  |   share_of_incumbent |
|:-------------|--------------------------:|:---------------------------------------------|---------------------:|
| inj_latest   |                      1343 | {'QB': 159, 'RB': 279, 'TE': 298, 'WR': 607} |               1      |
| inj_fresh1d  |                       475 | {'QB': 51, 'RB': 104, 'TE': 108, 'WR': 212}  |               0.3537 |
| inj_freshest |                       856 | {'QB': 90, 'RB': 179, 'TE': 185, 'WR': 402}  |               0.6374 |

## PRIMARY — week-clustered row-level paired deltas on the capture era

Sign convention: **positive = the tighter rung BEATS the incumbent**.

### `inj_fresh1d` vs `inj_latest`

| position   |    n |   n_clusters |   mean_delta |   naive_se |   clustered_se |   se_inflation_x | ci95_clustered       | spans_zero   |
|:-----------|-----:|-------------:|-------------:|-----------:|---------------:|-----------------:|:---------------------|:-------------|
| QB         | 1372 |           18 |     -0.06624 |    0.03161 |        0.0429  |             1.36 | [-0.15033, 0.01784]  | True         |
| RB         | 2144 |           18 |     -0.01794 |    0.01337 |        0.01735 |             1.3  | [-0.05194, 0.01606]  | True         |
| WR         | 3231 |           18 |     -0.04772 |    0.01405 |        0.0241  |             1.72 | [-0.09496, -0.00048] | False        |
| TE         | 1941 |           18 |     -0.01161 |    0.01247 |        0.01398 |             1.12 | [-0.03902, 0.01579]  | True         |
| ALL        | 8688 |           18 |     -0.03523 |    0.00842 |        0.01785 |             2.12 | [-0.07022, -0.00024] | False        |

### `inj_freshest` vs `inj_latest`

| position   |    n |   n_clusters |   mean_delta |   naive_se |   clustered_se |   se_inflation_x | ci95_clustered      | spans_zero   |
|:-----------|-----:|-------------:|-------------:|-----------:|---------------:|-----------------:|:--------------------|:-------------|
| QB         | 1372 |           18 |      0.00213 |    0.01362 |        0.01331 |             0.98 | [-0.02395, 0.02822] | True         |
| RB         | 2144 |           18 |      0.01364 |    0.00694 |        0.00529 |             0.76 | [0.00327, 0.024]    | False        |
| WR         | 3231 |           18 |     -0.01303 |    0.00917 |        0.01252 |             1.36 | [-0.03758, 0.01151] | True         |
| TE         | 1941 |           18 |      0.00173 |    0.01031 |        0.01154 |             1.12 | [-0.02089, 0.02435] | True         |
| ALL        | 8688 |           18 |     -0.00076 |    0.00495 |        0.00726 |             1.47 | [-0.01499, 0.01348] | True         |

### Multiplicity over the 8 reported comparisons (a reading aid, never a gate)

| arm          | position   |   mean_delta |   z_clustered |   p_two_sided |   bh_cutoff_q10 | survives_bh_q10   |
|:-------------|:-----------|-------------:|--------------:|--------------:|----------------:|:------------------|
| inj_freshest | RB         |      0.01364 |         2.578 |       0.00992 |          0.0125 | True              |
| inj_fresh1d  | WR         |     -0.04772 |        -1.98  |       0.04769 |          0.025  | False             |
| inj_fresh1d  | QB         |     -0.06624 |        -1.544 |       0.12257 |          0.0375 | False             |
| inj_freshest | WR         |     -0.01303 |        -1.041 |       0.298   |          0.05   | False             |
| inj_fresh1d  | RB         |     -0.01794 |        -1.034 |       0.30113 |          0.0625 | False             |
| inj_fresh1d  | TE         |     -0.01161 |        -0.83  |       0.40627 |          0.075  | False             |
| inj_freshest | QB         |      0.00213 |         0.16  |       0.87286 |          0.0875 | False             |
| inj_freshest | TE         |      0.00173 |         0.15  |       0.88083 |          0.1    | False             |

any comparison surviving BH q=0.1: **True**

## SECONDARY — the pre-registered stratified read

- **QB**: listed_fresh_le_1d n=51 Δ=1.83242 ±0.54858 · listed_stale_gt_1d n=108 Δ=0.61993 ±0.3989 · not_listed n=1213 Δ=0.00353 ±0.02459
- **RB**: listed_fresh_le_1d n=104 Δ=0.80084 ±0.35399 · listed_stale_gt_1d n=175 Δ=0.11316 ±0.13703 · not_listed n=1865 Δ=-0.00674 ±0.00871
- **WR**: listed_fresh_le_1d n=212 Δ=0.88445 ±0.16661 · listed_stale_gt_1d n=395 Δ=0.24184 ±0.09891 · not_listed n=2624 Δ=-0.00462 ±0.0097
- **TE**: listed_fresh_le_1d n=108 Δ=0.65606 ±0.12726 · listed_stale_gt_1d n=190 Δ=0.00544 ±0.14059 · not_listed n=1643 Δ=0.00544 ±0.00609

## ⭐ Cross-era stratum shares — can a freshness gradient explain the era gap?

**the capture era is FRESHER on this cut (0.354 vs 0.076 of listed rows within 1 day), so a freshness DEFICIT cannot explain its smaller lift — the within-2025 gradient is real but does not transfer into an era explanation**

|                  |   listed_rows |   share_fresh_le_1d |   share_stale_gt_1d |   median_age_days |   sd_age_days |   share_gt_2d |
|:-----------------|--------------:|--------------------:|--------------------:|------------------:|--------------:|--------------:|
| legacy(nflverse) |         14058 |              0.0756 |              0.9244 |             1.435 |         0.439 |        0.0394 |
| capture(2025)    |          1343 |              0.3537 |              0.6463 |             1.483 |         1.375 |        0.2695 |

⚠️ a legacy `date_modified` is the REPORT's own timestamp; a capture instant is when the page was photographed. Stamp age is not the same quantity across eras, so this comparison BOUNDS the freshness explanation rather than settling it.

## Fold-level CRPS (reported, NEVER gated)

| fold   |   n_test |   base_rate_RB |   inj_latest_RB |   inj_fresh1d_RB |   inj_freshest_RB |
|:-------|---------:|---------------:|----------------:|-----------------:|------------------:|
| 2024H1 |     4365 |         2.576  |          2.4432 |           2.4432 |            2.4432 |
| 2024H2 |     4212 |         2.5129 |          2.3438 |           2.3438 |            2.3438 |
| 2025H1 |     4308 |         2.4371 |          2.3951 |           2.4299 |            2.38   |
| 2025H2 |     4380 |         2.4625 |          2.4201 |           2.4215 |            2.4079 |

## Anchors

{
  "QB": {
    "nihilist_loses": true,
    "pos_marginal_loses": true,
    "incumbent_respects_own_form_oracle": true,
    "mean_crps": {
      "inj_latest": 2.5377,
      "nihilist_zero": 6.6483,
      "pos_marginal": 4.7852,
      "oracle_avail__inj": 2.1118
    }
  },
  "RB": {
    "nihilist_loses": true,
    "pos_marginal_loses": true,
    "incumbent_respects_own_form_oracle": true,
    "mean_crps": {
      "inj_latest": 2.4005,
      "nihilist_zero": 5.6859,
      "pos_marginal": 3.89,
      "oracle_avail__inj": 2.1751
    }
  },
  "WR": {
    "nihilist_loses": true,
    "pos_marginal_loses": true,
    "incumbent_respects_own_form_oracle": true,
    "mean_crps": {
      "inj_latest": 2.5428,
      "nihilist_zero": 5.4612,
      "pos_marginal": 3.7053,
      "oracle_avail__inj": 2.0604
    }
  },
  "TE": {
    "nihilist_loses": true,
    "pos_marginal_loses": true,
    "incumbent_respects_own_form_oracle": true,
    "mean_crps": {
      "inj_latest": 1.7727,
      "nihilist_zero": 3.585,
      "pos_marginal": 2.626,
      "oracle_avail__inj": 1.3701
    }
  }
}

## Verdict

**NO_CERTIFICATION_POSSIBLE** — by design (see the power ceiling). Direction read at row level: `inj_fresh1d` LOSES TO the incumbent pooled (Δ=-0.03523 ± 0.01785 clustered, CI95 [-0.07022, -0.00024], excludes zero) · `inj_freshest` TIES the incumbent pooled (Δ=-0.00076 ± 0.00726 clustered, CI95 [-0.01499, 0.01348], spans zero).

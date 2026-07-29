# NF-D11 — return-from-absence AVAILABILITY PRIOR (§0.5 bake-off)

**Generated:** 2026-07-29T18:04:00.592073+00:00 · **held-out target seasons:** 2017–2025 (9) · **configs scored:** 21 · **returner rows:** 457

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is selected here is how hard to DISCOUNT a player returning from a full missed season. The population is the one the old base-season anchor DELETED, so the honest baseline is not "a worse number" — it is NO NUMBER AT ALL.

## 0. The universe fix this prior serves

|   season |   board_without_rescue |   board_with_rescue |   rescued |   rescued_realized_ppr_mean |   rescued_who_played_ge6g |
|---------:|-----------------------:|--------------------:|----------:|----------------------------:|--------------------------:|
| 2017.000 |                666.000 |             699.000 |    33.000 |                      21.400 |                    12.000 |
| 2018.000 |                664.000 |             703.000 |    39.000 |                      30.500 |                    15.000 |
| 2019.000 |                680.000 |             716.000 |    36.000 |                      19.200 |                    11.000 |
| 2020.000 |                678.000 |             745.000 |    67.000 |                      14.700 |                    18.000 |
| 2021.000 |                704.000 |             758.000 |    54.000 |                      12.700 |                    12.000 |
| 2022.000 |                741.000 |             783.000 |    42.000 |                      17.300 |                    11.000 |
| 2023.000 |                711.000 |             764.000 |    53.000 |                      11.500 |                     8.000 |
| 2024.000 |                688.000 |             734.000 |    46.000 |                       6.000 |                    10.000 |
| 2025.000 |                699.000 |             786.000 |    87.000 |                       5.500 |                    15.000 |

## 1. Pre-registered candidate classes

| family | idea | fit |
|--------|------|-----|
| `none` | rescue with no prior (stale durability carried forward) | — (the null) |
| `flat` | one pooled empirical return level | in-fold mean |
| `tier` | level per pre-registered prior-production tier (<50 / 50–120 / >120 PPR) | in-fold per-cell mean |
| `missed` | level per seasons missed (1 vs ≥2) | in-fold per-cell mean |
| `ratio` | multiplicative haircut on the player's own expected games | in-fold returner/healthy ratio |
| `learned` | **direct-learned foil** — LS on (prior games, log1p prior PPR, seasons missed, QB) | in-fold OLS |

Each non-`none` family × blend ∈ {0.3, 0.5, 0.7, 1.0}. Every fit uses only return years ≤ the base season, so no config ever sees the season it is scored on.

## 2. Selection metric + the two-sided sanity anchors

Primary = **returner CRPS** of the emitted predictive vs the realized PPR total (cohort INCLUDES the ~43% who play zero games — the ρ backtest's ≥6-game filter would delete exactly the population this prior exists for).

⚠️ **MAE was the obvious first choice and it is SILENTLY BIASED here** (a live instance of the CLAUDE.md selection-metric-inversion landmine): MAE is minimised at the conditional MEDIAN, and the realized returner distribution is so zero-heavy (median 1 game, long right tail) that MAE pays for pessimism — the DEGENERATE arm below (project ZERO for every returner) BEATS the best real candidate on MAE (15.474 vs 18.9633). A metric a nihilist wins cannot select a projection. CRPS is a proper scoring rule (minimised by the true predictive) and grades the emitted point and spread JOINTLY — which is what these arms move together — and it reverses that ordering. MAE/RMSE remain reported, not selectable. Calibration is a **FLOOR** (`coverage_80 ≥ 0.80`), never a target to minimise distance to — a coverage TARGET rewards under-dispersion. Guard = whole-board ρ must not degrade.

**Anchors** — ORACLE (knows realized games) CRPS **9.475** · best candidate **13.5223** · DEGENERATE (project zero for every returner) CRPS **15.623**.

✅ nothing beats the oracle · ✅ the degenerate zero-projection loses.

## 3. Results — all configs (sorted by the primary metric)

| config                  |   CRPS |   CRPS high-tier |   CRPS mid |   CRPS low |   RMSE fp |   MAE fp |   MAE games |   bias fp |   cov80 |   proj g |   real g |   board ρ | eligible       |
|:------------------------|-------:|-----------------:|-----------:|-----------:|----------:|---------:|------------:|----------:|--------:|---------:|---------:|----------:|:---------------|
| ratio @ blend 1         | 13.522 |           30.500 |     17.078 |      9.336 |    26.927 |   18.963 |       3.846 |     6.565 |   0.915 |    4.152 |    3.753 |     0.755 | yes            |
| ratio @ blend 0.7       | 14.391 |           29.898 |     18.794 |     10.269 |    28.023 |   20.766 |       4.084 |    10.731 |   0.891 |    4.958 |    3.753 |     0.755 | yes            |
| tier @ blend 1          | 14.588 |           33.359 |     19.036 |      9.772 |    29.678 |   21.793 |       4.167 |     9.851 |   0.930 |    4.508 |    3.753 |     0.755 | yes            |
| learned @ blend 1       | 14.899 |           33.209 |     18.025 |     10.384 |    29.138 |   21.486 |       4.296 |     9.895 |   0.902 |    5.130 |    3.753 |     0.755 | yes            |
| tier @ blend 0.7        | 15.118 |           32.267 |     19.985 |     10.560 |    29.881 |   22.733 |       4.298 |    13.031 |   0.917 |    5.207 |    3.753 |     0.755 | yes            |
| ratio @ blend 0.5       | 15.173 |           30.174 |     20.214 |     10.998 |    29.266 |   22.189 |       4.281 |    13.508 |   0.837 |    5.492 |    3.753 |     0.755 | yes            |
| learned @ blend 0.7     | 15.375 |           31.990 |     19.460 |     11.025 |    29.281 |   22.599 |       4.411 |    13.062 |   0.855 |    5.641 |    3.753 |     0.755 | yes            |
| flat @ blend 1          | 15.557 |           36.351 |     18.323 |     10.630 |    31.959 |   22.900 |       4.388 |     8.110 |   0.916 |    4.546 |    3.753 |     0.754 | yes            |
| missed @ blend 1        | 15.567 |           36.259 |     18.357 |     10.666 |    31.959 |   22.900 |       4.388 |     8.110 |   0.920 |    4.546 |    3.753 |     0.754 | yes            |
| flat @ blend 0.7        | 15.641 |           32.635 |     19.365 |     11.244 |    30.802 |   23.365 |       4.455 |    11.813 |   0.912 |    5.231 |    3.753 |     0.755 | yes            |
| missed @ blend 0.7      | 15.645 |           32.560 |     19.378 |     11.272 |    30.802 |   23.365 |       4.455 |    11.813 |   0.920 |    5.231 |    3.753 |     0.755 | yes            |
| tier @ blend 0.5        | 15.684 |           32.012 |     20.966 |     11.209 |    30.540 |   23.589 |       4.424 |    15.151 |   0.856 |    5.672 |    3.753 |     0.755 | yes            |
| learned @ blend 0.5     | 15.885 |           31.734 |     20.710 |     11.552 |    30.000 |   23.561 |       4.522 |    15.174 |   0.818 |    5.983 |    3.753 |     0.755 | yes            |
| flat @ blend 0.5        | 15.976 |           31.436 |     20.489 |     11.728 |    30.849 |   23.914 |       4.532 |    14.281 |   0.871 |    5.691 |    3.753 |     0.755 | yes            |
| missed @ blend 0.5      | 15.976 |           31.370 |     20.485 |     11.749 |    30.849 |   23.914 |       4.532 |    14.281 |   0.884 |    5.691 |    3.753 |     0.755 | yes            |
| ratio @ blend 0.3       | 16.109 |           30.997 |     21.840 |     11.806 |    30.870 |   23.793 |       4.506 |    16.286 |   0.799 |    6.029 |    3.753 |     0.754 | NO (cov floor) |
| tier @ blend 0.3        | 16.408 |           32.150 |     22.213 |     11.940 |    31.596 |   24.597 |       4.587 |    17.272 |   0.780 |    6.134 |    3.753 |     0.754 | NO (cov floor) |
| missed @ blend 0.3      | 16.531 |           31.259 |     21.910 |     12.279 |    31.567 |   24.746 |       4.655 |    16.750 |   0.816 |    6.149 |    3.753 |     0.754 | yes            |
| flat @ blend 0.3        | 16.536 |           31.317 |     21.933 |     12.265 |    31.567 |   24.746 |       4.655 |    16.750 |   0.806 |    6.149 |    3.753 |     0.754 | yes            |
| learned @ blend 0.3     | 16.543 |           31.956 |     22.158 |     12.149 |    31.207 |   24.621 |       4.653 |    17.285 |   0.789 |    6.324 |    3.753 |     0.754 | NO (cov floor) |
| none (rescue, no prior) | 18.365 |           34.729 |     25.737 |     13.415 |    33.850 |   26.322 |       4.878 |    20.452 |   0.637 |    6.836 |    3.753 |     0.753 | NO (cov floor) |

## 3b. POPULATION-VALIDITY check — does the winner also win where it MATTERS?

The returner cohort is ~68% fringe players (best window season <50 PPR) who are undraftable whatever we project. A config could therefore win the pooled metric on the population NOBODY DRAFTS while losing on the handful of genuinely draftable returners — the Aiyuk/Dell case this whole story exists for. So the table above also carries CRPS stratified by the pre-registered prior-production tier.

**High-tier (>120 PPR window season, n = 48) winner: `ratio @ blend 0.7` (CRPS-high 29.8982); the shipped pooled winner `ratio @ blend 1` scores 30.5002 there — the SAME family, so the family choice is population-robust.**

The blend within that family is where the two populations disagree slightly (the high tier prefers a softer discount). That subset is ~5 players/season, so its preference sits well inside noise; ship the PRE-REGISTERED pooled winner rather than re-picking on a 50-row slice — re-picking there is precisely the overfitting the deflation below exists to catch. The tension is real and is recorded here rather than smoothed away.

## 4. Deflation — CSCV / PBO over held-out season splits

**PBO = 0.0** over 126 balanced season splits (median logit 3.045); config spread (best→worst CRPS) = 13.522 → 18.365 (35.8%).

Reading it (CLAUDE.md): a high PBO on a **TIED** field is the NULL — nothing robustly separates the candidates, which makes the incumbent choice proven rather than lucky. A high PBO with a **WIDE** spread is genuine overfitting. The spread above is the discriminator.

**Quadrant: LOW PBO (0.0) + WIDE spread (35.8%) ⇒ a genuinely separated winner** — the families are not interchangeable and the choice survives out-of-sample.

## 5. Selection

**SHIPPED: `ratio @ blend 1`** — returner CRPS 13.5223, RMSE 26.9272, MAE 18.9633, games MAE 3.8459, coverage 0.9151, board ρ 0.7552.

The prior EARNS its place: `ratio @ blend 1` cuts returner CRPS from 18.3647 (rescue-with-no-prior) to 13.5223, games MAE from 4.8784 to 3.8459, and lifts 80% coverage 0.6369 → 0.9151 (floor 0.80) with the whole-board ρ unmoved (0.7552 vs 0.7531).

## 6. Per-season detail (shipped config)

|   season |      n |   crps |   crps_high |   n_high |   crps_mid |   n_mid |   crps_low |   n_low |   rmse_fp |   mae_fp |   mae_games |   bias_fp |   coverage_80 |   mean_proj_games |   mean_real_games |   board_spearman_all |
|---------:|-------:|-------:|------------:|---------:|-----------:|--------:|-----------:|--------:|----------:|---------:|------------:|----------:|--------------:|------------------:|------------------:|---------------------:|
| 2017.000 | 33.000 | 16.462 |      33.199 |    6.000 |     21.761 |   5.000 |     10.693 |  22.000 |    32.265 |   24.631 |       4.341 |     5.278 |         0.818 |             4.910 |             5.210 |                0.749 |
| 2018.000 | 39.000 | 16.303 |      41.205 |    7.000 |     21.634 |   6.000 |      8.369 |  26.000 |    38.280 |   22.520 |       3.533 |     2.725 |         0.923 |             4.910 |             5.000 |                0.737 |
| 2019.000 | 36.000 | 16.319 |      47.488 |    7.000 |     16.079 |   5.000 |      7.279 |  24.000 |    35.017 |   23.076 |       3.699 |     5.696 |         0.917 |             4.440 |             3.890 |                0.727 |
| 2020.000 | 67.000 | 13.935 |      26.804 |    9.000 |     15.007 |  12.000 |     11.138 |  46.000 |    24.026 |   19.502 |       4.264 |    11.499 |         0.925 |             4.650 |             3.820 |                0.743 |
| 2021.000 | 54.000 | 14.327 |      24.127 |    5.000 |     20.759 |  14.000 |     10.354 |  35.000 |    27.375 |   19.675 |       4.236 |     8.870 |         0.926 |             4.010 |             3.670 |                0.745 |
| 2022.000 | 42.000 | 13.991 |      20.573 |    4.000 |     22.731 |   6.000 |     11.529 |  32.000 |    24.685 |   19.230 |       3.988 |     4.780 |         0.881 |             3.970 |             3.290 |                0.753 |
| 2023.000 | 53.000 | 12.823 |      36.118 |    6.000 |     10.309 |   8.000 |      9.754 |  39.000 |    29.094 |   18.103 |       3.470 |     6.969 |         0.925 |             3.750 |             2.470 |                0.747 |
| 2024.000 | 46.000 |  8.071 |      29.761 |    1.000 |      9.857 |   6.000 |      7.240 |  39.000 |    14.539 |   10.853 |       3.820 |     6.565 |         0.978 |             3.600 |             3.980 |                0.790 |
| 2025.000 | 87.000 |  9.470 |      15.227 |    3.000 |     15.565 |  17.000 |      7.666 |  67.000 |    17.064 |   13.080 |       3.262 |     6.705 |         0.943 |             3.130 |             2.450 |                0.806 |

## 7. Honest limitations

- **The historical cohort is reconstructed from the WEEKLY-ROSTER branch only** — `stg_nfl_depth_charts_current` has no historical partitions, so the live 2026 board rescues a slightly LARGER set than the ablation could measure (a depth-chart row is, if anything, stronger evidence of being in the league than an ACT roster row).
- **The prior discounts GAMES, not the per-game line** — a returner's production line is his last healthy season's, blended over the recency window. Age/scheme/role drift since then is unmodelled; the widened band and `confidence = low` are the honest surface.
- **`n` is small by construction** (~40–50 returners/season). The tier cells are the smallest; a cell under the minimum falls back to the pooled returner mean rather than a noisy estimate.
- **The board will FADE the market on returners, by design.** The fitted haircut is harsher than draft-room optimism: on the 2026 board Tank Dell projects WR95 against an ADP of ~157 overall and Brandon Aiyuk WR112 against ~148. That gap is the whole point — 431 historical returners say a full-season absence costs far more availability than a draft board prices — but it is a FADE, not a hidden claim: the ADP column renders beside our rank on every surface, the band's p90 still covers a healthy season, and `confidence = low` says out loud that this is the least certain row on the board.
- **No edge claim.** This is a projection-quality fix: it restores draftable players to the board with honest bands, not a market edge.


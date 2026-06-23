# E13.8 — Market-Accuracy Benchmark: year × book line quality (H2H + totals)

**Story:** E13.8 (Model-A · situational awareness · advisory/transparency only)
**Date:** 2026-06-23
**Frame:** *"What are we targeting?"* — how accurate is the **market itself** at setting lines, per book, per year, so we know the bar before re-opening MLB totals/H2H. **No +EV claim. This is a benchmark, not a signal.**

---

## 0. TL;DR — what we're targeting

1. **The ceiling is thin.** Pinnacle (and the low-vig sharps `betonlineag` / `lowvig` / `onexbet`, which match it within noise) close H2H at **Brier ≈ 0.245**, which beats the home-base-rate no-skill floor (**≈ 0.249**) by only **~0.002–0.005 — and not even every season** (2023 and the partial 2026 sit *at or above* the floor). A "great" H2H model therefore only has to be **calibrated to ~0.245 Brier**; there is essentially **no headroom to beat the close** — this re-confirms E13.6 and the dead-H2H-edge thesis.
2. **The totals over/under PRICE is a coin flip** at this horizon. *Every* book including Pinnacle sits at **Brier ≈ 0.250 = the no-skill floor**, with over-rate **0.49–0.51** (lines are well-centered, no directional bias to exploit). The only information totals carries is in the **NUMBER itself**: line **MAE ≈ 3.4–3.7 runs** (Pinnacle best at ~3.37–3.60), and that error is **irreducibly noisy** (RMSE ≈ 4.5 — a single game swings ±4.5 runs around the line).
3. **The soft-book spread is tiny.** Across well-covered US books the 2025 H2H Brier range is **~0.243–0.249** and totals **~0.249–0.251** — mostly inside sampling noise. The cleaner book-quality axis is **vig** (sharps 1.6–3% vs retail 4–8%), not calibration. Any residual edge would live in *price* (vig), not in *mispriced probability*.
4. **No year-over-year sharpening in Brier** (Brier is dominated by how predictable each season's outcomes happened to be — 2022 was "predictable," 2023 was not). Soft-book convergence toward the sharp **is** visible in `mean_abs_dist_to_sharp` (e.g. Bovada H2H 0.018 → 0.006 from 2021 → 2025), exactly as E3.0b found.
5. **Net for the re-eval:** totals is still the open question, but the question is about the **number**, not the over/under odds; and the bar to "match the market" is **low on calibration but has ~zero edge headroom**. The product goal stays **calibration-parity with the close**, not beating it.

> ⚠️ **Read the close caveat (§4) first.** "Close" here = last snapshot **before game-day 00:00 UTC** (~18–24h pre-game), the leakage-safe guard inherited from E3.0b/E4.3 — **not** the minutes-before-pitch close. Every accuracy number below is a **conservative lower bound** on true closing-line sharpness.

---

## 1. Reference anchors (no-skill floors)

The interpretive baselines. A book has **calibration skill** only if its closing Brier is **below** the base-rate floor; the coin-flip floor (predict 0.5 for everyone) is **0.2500** for both markets.

| Market | Season | n_games | base rate | no-skill Brier (base-rate) |
|--------|:------:|-------:|:---------:|:--------------------------:|
| h2h    | 2021 | 1,547 | home 0.529 | **0.2491** |
| h2h    | 2022 | 1,653 | home 0.548 | **0.2477** |
| h2h    | 2023 | 1,686 | home 0.520 | **0.2496** |
| h2h    | 2024 | 1,683 | home 0.525 | **0.2494** |
| h2h    | 2025 | 1,462 | home 0.551 | **0.2474** |
| h2h    | 2026\* | 842  | home 0.543 | **0.2482** |
| totals | 2021 | 1,454 | over 0.490 | **0.2499** |
| totals | 2022 | 1,547 | over 0.483 | **0.2497** |
| totals | 2023 | 1,581 | over 0.502 | **0.2500** |
| totals | 2024 | 1,577 | over 0.502 | **0.2500** |
| totals | 2025 | 1,365 | over 0.498 | **0.2500** |
| totals | 2026\* | 772  | over 0.513 | **0.2498** |

- **Totals over-rate ≈ 0.50 every season** → the market posts **well-centered** totals lines; there is no standing over/under directional bias. (Over-rate computed on non-push games vs the Pinnacle close line.)
- **`*` 2026 is a partial, in-progress season** (~840 games through 2026-06) — treat as directional only.
- E13.6 prior: the *served* market H2H Brier sits ~**0.247** — i.e. right on the floor. The numbers below corroborate that.

---

## 2. Part A — canonical 4 books, year × book (both markets)

Reproduces E3.0b's `feature_edge_book_market_era_quality` grain (book ∈ {pinnacle, bovada, caesars, fanduel}). **Pinnacle = the sharp anchor / ceiling** (`dist_to_sharp` ≡ 0 by construction). Lower Brier / log-loss / vig / dist = sharper.

### 2A. H2H — closing Brier · log-loss · vig · dist-to-sharp · favorite hit-rate

| book | season | n | brier | log-loss | vig | dist→sharp | fav hit-rate |
|------|:-----:|----:|:-----:|:--------:|:----:|:----------:|:-----------:|
| **pinnacle** | 2021 | 1,547 | **0.2464** | 0.6879 | 0.0256 | 0.000 | 0.565 |
| **pinnacle** | 2022 | 1,653 | **0.2404** | 0.6753 | 0.0247 | 0.000 | 0.600 |
| **pinnacle** | 2023 | 1,686 | **0.2515** | 0.7021 | 0.0246 | 0.000 | 0.562 |
| **pinnacle** | 2024 | 1,683 | **0.2450** | 0.6851 | 0.0239 | 0.000 | 0.570 |
| **pinnacle** | 2025 | 1,462 | **0.2452** | 0.6843 | 0.0262 | 0.000 | 0.557 |
| **pinnacle** | 2026\* | 842 | **0.2553** | 0.7117 | 0.0274 | 0.000 | 0.548 |
| bovada | 2021 | 1,545 | 0.2441 | 0.6830 | 0.0423 | 0.0180 | 0.576 |
| bovada | 2022 | 1,595 | 0.2424 | 0.6803 | 0.0475 | 0.0151 | 0.592 |
| bovada | 2023 | 1,546 | 0.2524 | 0.7044 | 0.0479 | 0.0143 | 0.567 |
| bovada | 2024 | 1,372 | 0.2452 | 0.6860 | 0.0484 | 0.0118 | 0.578 |
| bovada | 2025 | 1,448 | 0.2453 | 0.6846 | 0.0474 | 0.0100 | 0.557 |
| bovada | 2026\* | 788 | 0.2560 | 0.7123 | 0.0491 | 0.0200 | 0.555 |
| caesars | 2021 | 1,499 | 0.2418 | 0.6764 | 0.0214 | 0.0211 | 0.574 |
| caesars | 2022 | 1,675 | 0.2367 | 0.6662 | 0.0401 | 0.0206 | 0.601 |
| caesars | 2023 | 1,742 | 0.2425 | 0.6778 | 0.0429 | 0.0259 | 0.575 |
| caesars | 2024 | 1,717 | 0.2457 | 0.6875 | 0.0450 | 0.0139 | 0.574 |
| caesars | 2025 | 1,479 | 0.2491 | 0.6933 | 0.0447 | 0.0146 | 0.544 |
| caesars | 2026\* | 874 | 0.2554 | 0.7121 | 0.0457 | 0.0233 | 0.542 |
| fanduel | 2021 | 1,421 | 0.2463 | 0.6915 | 0.0435 | 0.0173 | 0.576 |
| fanduel | 2022 | 1,706 | 0.2410 | 0.6775 | 0.0433 | 0.0131 | 0.601 |
| fanduel | 2023 | 1,760 | 0.2525 | 0.7053 | 0.0431 | 0.0172 | 0.563 |
| fanduel | 2024 | 1,902 | 0.2462 | 0.6889 | 0.0427 | 0.0175 | 0.572 |
| fanduel | 2025 | 2,003 | 0.2458 | 0.6859 | 0.0423 | 0.0156 | 0.553 |
| fanduel | 2026\* | 950 | 0.2562 | 0.7147 | 0.0437 | 0.0272 | 0.545 |

**Read:** H2H closing Brier clusters in **0.240–0.256** across all four books — i.e. **right on the 0.249 no-skill floor**. Pinnacle beats the floor in 4/6 seasons by ~0.002–0.007 and ties/loses it in 2023 & 2026\*. Favorite hit-rate is the more legible skill signal: the de-vigged favorite wins **~55–60%** consistently. Note **Pinnacle is not always the lowest Brier** (Caesars-2022 0.2367, low-vig books below beat it) — within-noise ties, so "ceiling" = *sharp anchor by vig & convention*, not a strict Brier minimum.

### 2B. Totals — closing Brier · vig · dist-to-sharp · line MAE · line RMSE · push rate

| book | season | n | brier | vig | dist→sharp | line MAE | line RMSE | push rate |
|------|:-----:|----:|:-----:|:----:|:----------:|:--------:|:---------:|:---------:|
| **pinnacle** | 2021 | 1,454 | **0.2504** | 0.0337 | 0.000 | 3.594 | 4.613 | 0.036 |
| **pinnacle** | 2022 | 1,547 | **0.2493** | 0.0325 | 0.000 | 3.412 | 4.441 | 0.044 |
| **pinnacle** | 2023 | 1,581 | **0.2495** | 0.0323 | 0.000 | 3.714 | 4.688 | 0.040 |
| **pinnacle** | 2024 | 1,577 | **0.2501** | 0.0318 | 0.000 | 3.371 | 4.344 | 0.040 |
| **pinnacle** | 2025 | 1,365 | **0.2498** | 0.0322 | 0.000 | 3.601 | 4.635 | 0.048 |
| **pinnacle** | 2026\* | 772 | **0.2497** | 0.0360 | 0.000 | 3.563 | 4.568 | 0.055 |
| bovada | 2021 | 1,428 | 0.2497 | 0.0489 | 0.0118 | 3.603 | 4.637 | 0.043 |
| bovada | 2022 | 1,195 | 0.2489 | 0.0508 | 0.0131 | 3.391 | 4.417 | 0.046 |
| bovada | 2023 | 1,287 | 0.2502 | 0.0509 | 0.0099 | 3.753 | 4.756 | 0.037 |
| bovada | 2024 | 1,285 | 0.2496 | 0.0507 | 0.0062 | 3.344 | 4.317 | 0.041 |
| bovada | 2025 | 1,355 | 0.2500 | 0.0495 | 0.0060 | 3.594 | 4.617 | 0.044 |
| bovada | 2026\* | 730 | 0.2494 | 0.0515 | 0.0087 | 3.537 | 4.546 | 0.050 |
| caesars | 2021 | 1,262 | 0.2501 | 0.0466 | 0.0101 | 3.554 | 4.590 | 0.052 |
| caesars | 2022 | 1,566 | 0.2489 | 0.0463 | 0.0143 | 3.362 | 4.340 | 0.043 |
| caesars | 2023 | 1,622 | 0.2500 | 0.0465 | 0.0135 | 3.622 | 4.599 | 0.043 |
| caesars | 2024 | 1,618 | 0.2510 | 0.0493 | 0.0156 | 3.388 | 4.352 | 0.032 |
| caesars | 2025 | 1,395 | 0.2505 | 0.0492 | 0.0136 | 3.668 | 4.711 | 0.042 |
| caesars | 2026\* | 826 | 0.2494 | 0.0504 | 0.0153 | 3.543 | 4.509 | 0.044 |
| fanduel | 2021 | 575 | 0.2503 | 0.0514 | 0.0111 | 3.484 | 4.414 | 0.035 |
| fanduel | 2022 | 1,610 | 0.2496 | 0.0504 | 0.0125 | 3.405 | 4.421 | 0.038 |
| fanduel | 2023 | 1,692 | 0.2501 | 0.0503 | 0.0175 | 3.710 | 4.701 | 0.032 |
| fanduel | 2024 | 1,851 | 0.2502 | 0.0507 | 0.0188 | 3.422 | 4.371 | 0.026 |
| fanduel | 2025 | 1,934 | 0.2501 | 0.0507 | 0.0174 | 3.610 | 4.625 | 0.033 |
| fanduel | 2026\* | 921 | 0.2484 | 0.0523 | 0.0189 | 3.552 | 4.515 | 0.030 |

**Read:** Totals closing Brier is **pinned to ~0.250 (= no-skill) for every book, every season** — the over/under **price** carries **no measurable calibration skill** at this horizon. All the signal is in the **number**: line MAE **~3.34–3.75 runs**, RMSE **~4.3–4.8**. Pinnacle/Bovada are at the low end of MAE but the cross-book gap is tiny and noise-dominated. **Push-rate ~3–5%** for books posting whole+half-run lines (see §3 for books that post half-run-only and never push).

---

## 3. Part B — widened book set (full oddsapi census)

The mart hard-codes 4 books; the E13.8 analysis (`dbt/analyses/e13_8_market_accuracy_benchmark.sql`) generalizes to **every** oddsapi book (~50). Below is the **2025 full-season** cross-book slice for a representative sharp+retail+offshore set (the complete year×book census for all books & seasons is reproducible from the analysis SQL — §5). Sorted by H2H Brier.

### 3A. H2H 2025 — cross-book

| book | n | brier | vig | dist→sharp | fav hit-rate | tier |
|------|----:|:-----:|:----:|:----------:|:-----------:|------|
| betonlineag | 1,855 | 0.2426 | 0.0240 | 0.0181 | 0.559 | sharp/low-vig |
| lowvig      | 1,854 | 0.2426 | 0.0240 | 0.0181 | 0.559 | sharp/low-vig |
| onexbet     | 1,958 | 0.2431 | 0.0393 | 0.0203 | 0.557 | sharp/low-vig |
| betus       | 1,736 | 0.2435 | 0.0263 | 0.0184 | 0.555 | offshore |
| betrivers   | 1,143 | 0.2441 | 0.0507 | 0.0243 | 0.557 | retail |
| mybookieag  | 1,820 | 0.2444 | 0.0418 | 0.0117 | 0.549 | offshore |
| **pinnacle**| 1,462 | **0.2452** | 0.0262 | 0.000 | 0.557 | **sharp anchor** |
| bovada      | 1,448 | 0.2453 | 0.0474 | 0.0100 | 0.557 | offshore |
| draftkings  | 1,830 | 0.2456 | 0.0482 | 0.0138 | 0.555 | retail |
| fanduel     | 2,003 | 0.2458 | 0.0423 | 0.0156 | 0.553 | retail |
| espnbet     | 1,858 | 0.2465 | 0.0462 | 0.0147 | 0.557 | retail |
| fanatics    | 1,843 | 0.2466 | 0.0476 | 0.0136 | 0.554 | retail |
| betmgm      | 1,801 | 0.2467 | 0.0461 | 0.0156 | 0.554 | retail |
| caesars     | 1,479 | 0.2491 | 0.0447 | 0.0146 | 0.544 | retail |

**Spread:** best-to-worst **0.2426 → 0.2491 = 0.0065 Brier**, but most books sit within **±0.002** of each other — inside the ~±0.004 Brier sampling band at n≈1,500. The honest reading is **no significant calibration gap** between sharp and retail at the close. The real separator is **vig**: sharps 1.6–3% vs retail 4–5% (and `pointsbetus`/`fliff`/`winamax_fr` reach 6–8.5% — full census). **Several low-vig books edge Pinnacle on point-estimate Brier** — these are within-noise ties, not a sharper-than-Pinnacle claim.

### 3B. Totals 2025 — cross-book (line accuracy is the real axis)

| book | n_priced | brier | vig | line MAE | line RMSE | push rate |
|------|--------:|:-----:|:----:|:--------:|:---------:|:---------:|
| betus       | 1,704 | 0.2497 | 0.0462 | 3.563 | 4.551 | 0.045 |
| betonlineag | 1,811 | 0.2498 | 0.0462 | 3.544 | 4.517 | 0.043 |
| lowvig      | 1,810 | 0.2497 | 0.0344 | 3.546 | 4.519 | 0.043 |
| onexbet     | 1,934 | 0.2488 | 0.0397 | 3.580 | 4.563 | **0.000** |
| **pinnacle**| 1,433 | 0.2498 | 0.0322 | **3.601** | 4.635 | 0.048 |
| bovada      | 1,418 | 0.2500 | 0.0495 | 3.594 | 4.617 | 0.044 |
| mybookieag  | 1,801 | 0.2500 | 0.0532 | 3.601 | 4.630 | 0.049 |
| betmgm      | 1,765 | 0.2503 | 0.0485 | 3.597 | 4.600 | 0.040 |
| fanduel     | 1,999 | 0.2501 | 0.0507 | 3.610 | 4.625 | 0.033 |
| draftkings  | 1,789 | 0.2506 | 0.0497 | 3.604 | 4.620 | 0.043 |
| caesars     | 1,456 | 0.2505 | 0.0492 | 3.668 | 4.711 | 0.042 |
| espnbet     | 1,844 | 0.2493 | 0.0473 | 3.638 | 4.641 | **0.000** |
| fanatics    | 1,786 | 0.2509 | 0.0491 | 3.624 | 4.640 | 0.038 |

**Spread:** line MAE **3.54 → 3.67 runs** across the set — a ~0.13-run gap that is well inside the noise (RMSE ~4.5–4.7). Brier is uniformly ~0.250. **`espnbet` / `onexbet` (and `fliff`, `hardrockbet`, `sisportsbook`, recent `sport888`) post half-run-only totals → push rate ≈ 0** — a line-policy artifact, not accuracy. **Conclusion: no book sets a meaningfully more accurate totals number than another; the limit is irreducible game variance, not book skill.**

---

## 4. ⚠️ Methodology & the "close" caveat (read before quoting any number)

- **De-vig:** two-way additive de-vig of the close, `american_to_implied_sql` macro for **exact parity** with the warehouse + Python serve-time de-vig. Reference side: h2h = home, totals = over.
- **Leakage guard (preserved from E3.0b/E4.3):** `snapshot_ts < game_date`. Because `game_date` is a DATE, this keeps only snapshots **before game-day 00:00 UTC** → the "close" used here is the **last snapshot ~18–24h before first pitch**, *not* the minutes-before-pitch close. **Every Brier/MAE here is a conservative LOWER BOUND on true closing sharpness** — the real close would be modestly sharper, which is part of why H2H Brier sits on the floor and totals Brier sits exactly at no-skill. This is the honest, leakage-safe frame; it is consistent across all books/years so **cross-book and cross-year comparisons are valid**, but the **absolute** level understates the true close.
- **Pushes:** excluded from Brier/log-loss (outcome NULL); counted for `push_rate`.
- **`williamhill_us` folded into `caesars`** (canonical bookmaker map). `williamhill` (no `_us`) is a separate EU book, kept distinct.
- **Brier sampling band:** at n≈1,500, Brier SE ≈ ±0.003–0.004; treat sub-0.005 cross-book gaps as ties.
- **2026 is partial** (~840 games, in-progress) — directional only.

---

## 5. Reproduce

The full year × book × market census (all ~50 books, all metrics) is a single compiled analysis — **zero warehouse cost** (compiled by `dbtf compile`, never materialized/scheduled):

```bash
# Compile-check (CI parity):
dbtf compile --select e13_8_market_accuracy_benchmark
# Run ad-hoc to refresh the benchmark (compiled SQL is at
#   dbt/target/compiled/.../analyses/e13_8_market_accuracy_benchmark.sql ):
dbtf show --select e13_8_market_accuracy_benchmark --limit 1000
#   (or paste the compiled SQL into the Snowflake MCP / a worksheet)
```

Filter thin cells in any consumer with `n_games_priced >= 150`. The canonical-4 subset (Part A) reproduces E3.0b's `feature_edge_book_market_era_quality` exactly (same de-vig, close, leakage guard).

---

## 6. Feeds

- **Totals re-eval (E2.3 / E13.4 lift-tests):** the bar to beat is **line MAE ~3.4–3.6 runs / RMSE ~4.5** and **Brier 0.250 (= no-skill on the price)**. A totals model is "great" if it **matches** that calibration; the over/under price offers no edge headroom, so any totals value must come from a **sharper number** than the book posts — and §3B shows that number is already near the variance floor.
- **H2H re-eval:** ceiling = **Brier ~0.245, band ~0.43–0.57** (cf. E13.6 calibrator T=6.30). Edge is dead; **target calibration-parity with the close, do not chase Brier below the floor.**
